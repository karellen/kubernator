# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2026 Karellen, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#


from gevent.monkey import patch_all, is_anything_patched

if not is_anything_patched():
    patch_all()

import json
import unittest
from unittest.mock import MagicMock


def _make_api_exception(status, reason, message="boom"):
    from kubernetes.client import ApiException
    e = ApiException(status=status)
    e.body = json.dumps({"reason": reason, "message": message,
                         "status": "Failure", "details": {}})
    e.headers = {"content-type": "application/json"}
    return e


class K8sApplyRetryTest(unittest.TestCase):
    def _make_resource(self, *, name="cm", namespace="default",
                       remote_data="old", merged_data="new"):
        from kubernator.plugins.k8s_api import K8SResource, K8SResourceDef, K8SResourceDefKey
        manifest = {"apiVersion": "v1", "kind": "ConfigMap",
                    "metadata": {"name": name, "namespace": namespace},
                    "data": {"a": merged_data, "b": "x"}}
        rdef = K8SResourceDef(K8SResourceDefKey("", "v1", "ConfigMap"),
                              "configmap", "configmaps", True, False, None)
        rdef.populate_api = MagicMock()  # bypass real client wiring

        resource = K8SResource(manifest, rdef, source="unit")
        # Mock cluster I/O
        resource.get = MagicMock(return_value={
            "apiVersion": "v1", "kind": "ConfigMap",
            "metadata": {"name": name, "namespace": namespace,
                         "uid": "u1", "resourceVersion": "1"},
            "data": {"a": remote_data, "b": "x"}})
        # SSA dry-run merge: returns server's view; resourceVersion advances per call
        merged_v2 = {"apiVersion": "v1", "kind": "ConfigMap",
                     "metadata": {"name": name, "namespace": namespace,
                                  "uid": "u1", "resourceVersion": "2"},
                     "data": {"a": merged_data, "b": "x"}}
        merged_v3 = {"apiVersion": "v1", "kind": "ConfigMap",
                     "metadata": {"name": name, "namespace": namespace,
                                  "uid": "u1", "resourceVersion": "3"},
                     "data": {"a": merged_data, "b": "x"}}
        resource.patch = MagicMock(side_effect=[merged_v2, merged_v3])
        return resource

    def _make_plugin(self):
        plugin = MagicMock()
        plugin.context.k8s.client = MagicMock()
        plugin.context.k8s.immutable_changes = {}
        plugin._filter_resource_patch = lambda patch, excludes: list(patch)
        return plugin

    def test_409_on_patch_triggers_retry_and_succeeds(self):
        from kubernator.plugins.k8s import KubernetesPlugin

        plugin = self._make_plugin()
        resource = self._make_resource()

        applied_manifest = {"applied": True}
        patch_func = MagicMock(side_effect=[
            _make_api_exception(409, "Conflict", "stale resourceVersion"),
            applied_manifest,
        ])
        create_func = MagicMock()
        delete_func = MagicMock()

        result = KubernetesPlugin._apply_resource(
            plugin, False, [], resource,
            patch_func, create_func, delete_func, "")

        self.assertEqual(result, (0, 1, 0, applied_manifest))
        # patch_func called twice: first 409, then success
        self.assertEqual(patch_func.call_count, 2)
        # SSA dry-run merge re-issued on retry to compute a fresh patch
        self.assertEqual(resource.patch.call_count, 2)
        # No create or delete should have happened
        create_func.assert_not_called()
        delete_func.assert_not_called()

    def test_non_409_exception_on_patch_propagates_without_retry(self):
        from kubernator.plugins.k8s import KubernetesPlugin

        plugin = self._make_plugin()
        resource = self._make_resource()

        patch_func = MagicMock(side_effect=[
            _make_api_exception(500, "InternalError", "kaboom"),
        ])
        create_func = MagicMock()
        delete_func = MagicMock()

        with self.assertRaises(Exception) as ctx:
            KubernetesPlugin._apply_resource(
                plugin, False, [], resource,
                patch_func, create_func, delete_func, "")

        self.assertEqual(getattr(ctx.exception, "status", None), 500)
        # Single attempt, no retry
        self.assertEqual(patch_func.call_count, 1)
        self.assertEqual(resource.patch.call_count, 1)
