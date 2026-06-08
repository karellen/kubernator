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

import re
import unittest
from unittest.mock import MagicMock


class K8sFilterResourcePatchTest(unittest.TestCase):
    def _make_plugin(self):
        plugin = MagicMock()
        return plugin

    def test_test_only_patch_returns_empty(self):
        from kubernator.plugins.k8s import KubernetesPlugin

        plugin = self._make_plugin()
        patch = [
            {"op": "test", "path": "/metadata/uid", "value": "abc-123"},
            {"op": "test", "path": "/metadata/resourceVersion", "value": "42"},
        ]

        result = KubernetesPlugin._filter_resource_patch(plugin, patch, [])

        self.assertEqual(result, [])

    def test_patch_with_mutations_preserves_tests_and_mutations(self):
        from kubernator.plugins.k8s import KubernetesPlugin

        plugin = self._make_plugin()
        patch = [
            {"op": "replace", "path": "/data/key", "value": "new"},
            {"op": "test", "path": "/metadata/uid", "value": "abc-123"},
            {"op": "test", "path": "/metadata/resourceVersion", "value": "42"},
        ]

        result = KubernetesPlugin._filter_resource_patch(plugin, patch, [])

        self.assertEqual(result, patch)

    def test_excluded_mutations_leave_only_tests_returns_empty(self):
        from kubernator.plugins.k8s import KubernetesPlugin

        plugin = self._make_plugin()
        patch = [
            {"op": "replace", "path": "/data/key", "value": "new"},
            {"op": "add", "path": "/data/other", "value": "val"},
            {"op": "test", "path": "/metadata/uid", "value": "abc-123"},
            {"op": "test", "path": "/metadata/resourceVersion", "value": "42"},
        ]
        excludes = [re.compile(r"/data/.*")]

        result = KubernetesPlugin._filter_resource_patch(plugin, patch, excludes)

        self.assertEqual(result, [])

    def test_partial_exclude_preserves_remaining_mutations(self):
        from kubernator.plugins.k8s import KubernetesPlugin

        plugin = self._make_plugin()
        patch = [
            {"op": "replace", "path": "/data/key", "value": "new"},
            {"op": "replace", "path": "/spec/replicas", "value": 3},
            {"op": "test", "path": "/metadata/uid", "value": "abc-123"},
            {"op": "test", "path": "/metadata/resourceVersion", "value": "42"},
        ]
        excludes = [re.compile(r"/data/.*")]

        result = KubernetesPlugin._filter_resource_patch(plugin, patch, excludes)

        self.assertEqual(result, [
            {"op": "replace", "path": "/spec/replicas", "value": 3},
            {"op": "test", "path": "/metadata/uid", "value": "abc-123"},
            {"op": "test", "path": "/metadata/resourceVersion", "value": "42"},
        ])

    def test_empty_patch_returns_empty(self):
        from kubernator.plugins.k8s import KubernetesPlugin

        plugin = self._make_plugin()

        result = KubernetesPlugin._filter_resource_patch(plugin, [], [])

        self.assertEqual(result, [])
