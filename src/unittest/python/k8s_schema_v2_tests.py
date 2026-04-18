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

import unittest
from unittest.mock import MagicMock, patch

from kubernator.api import PropertyDict
from kubernator.plugins.k8s_api import K8SResourceDefKey
from kubernator.plugins.k8s_schema.v2 import SwaggerV2Validator


SWAGGER_FIXTURE = {
    "paths": {
        "/api/v1/namespaces/{namespace}/configmaps": {
            "get": {
                "x-kubernetes-action": "list",
                "x-kubernetes-group-version-kind": {
                    "group": "", "version": "v1", "kind": "ConfigMap"},
            },
            "post": {
                "x-kubernetes-action": "post",
                "x-kubernetes-group-version-kind": {
                    "group": "", "version": "v1", "kind": "ConfigMap"},
            },
        },
        "/apis/apps/v1/namespaces/{namespace}/deployments": {
            "get": {
                "x-kubernetes-action": "list",
                "x-kubernetes-group-version-kind": {
                    "group": "apps", "version": "v1", "kind": "Deployment"},
            },
        },
    },
    "definitions": {
        "io.k8s.api.core.v1.ConfigMap": {
            "type": "object",
            "x-kubernetes-group-version-kind": [
                {"group": "", "version": "v1", "kind": "ConfigMap"}],
            "required": ["apiVersion", "kind"],
            "properties": {
                "apiVersion": {"type": "string"},
                "kind": {"type": "string"},
                "metadata": {"type": "object", "properties": {
                    "name": {"type": "string"}, "namespace": {"type": "string"}},
                    "required": ["name"]},
                "data": {"type": "object",
                         "additionalProperties": {"type": "string"}},
            },
        },
        "io.k8s.api.apps.v1.Deployment": {
            "type": "object",
            "x-kubernetes-group-version-kind": [
                {"group": "apps", "version": "v1", "kind": "Deployment"}],
            "required": ["apiVersion", "kind"],
            "properties": {
                "apiVersion": {"type": "string"},
                "kind": {"type": "string"},
                "metadata": {"type": "object", "properties": {
                    "name": {"type": "string"}}, "required": ["name"]},
                "spec": {"type": "object", "properties": {
                    "replicas": {"type": "integer"}}},
            },
        },
    },
}


def _make_validator():
    ctx = PropertyDict()
    ctx.k8s = dict(server_git_version="v1.28.3")
    v = SwaggerV2Validator(ctx)
    with patch("kubernator.plugins.k8s_schema.v2.load_remote_file",
               return_value=SWAGGER_FIXTURE):
        v.load()
    return v


class SwaggerV2ValidatorTest(unittest.TestCase):
    def test_load_populates_definitions_for_both_gvks(self):
        v = _make_validator()
        self.assertIn(K8SResourceDefKey("", "v1", "ConfigMap"),
                      v.resource_definitions)
        self.assertIn(K8SResourceDefKey("apps", "v1", "Deployment"),
                      v.resource_definitions)

    def test_api_versions_contains_core_and_apps(self):
        v = _make_validator()
        api_versions = list(v.api_versions())
        self.assertIn("v1", api_versions)
        self.assertIn("apps/v1", api_versions)

    def test_iter_errors_passes_valid_manifest(self):
        v = _make_validator()
        rdef = v.resource_definitions[K8SResourceDefKey("", "v1", "ConfigMap")]
        manifest = {"apiVersion": "v1", "kind": "ConfigMap",
                    "metadata": {"name": "cm"},
                    "data": {"a": "1", "b": "2"}}
        self.assertEqual(list(v.iter_errors(manifest, rdef)), [])

    def test_iter_errors_rejects_wrong_type(self):
        v = _make_validator()
        rdef = v.resource_definitions[K8SResourceDefKey("apps", "v1", "Deployment")]
        manifest = {"apiVersion": "apps/v1", "kind": "Deployment",
                    "metadata": {"name": "d"},
                    "spec": {"replicas": "three"}}  # should be integer
        errors = list(v.iter_errors(manifest, rdef))
        self.assertTrue(errors, "expected errors for non-integer replicas")

    def test_iter_errors_accepts_old_manifest_kwarg(self):
        v = _make_validator()
        rdef = v.resource_definitions[K8SResourceDefKey("", "v1", "ConfigMap")]
        manifest = {"apiVersion": "v1", "kind": "ConfigMap",
                    "metadata": {"name": "cm"},
                    "data": {"a": "1"}}
        # should not raise; v2 ignores old_manifest
        self.assertEqual(
            list(v.iter_errors(manifest, rdef, old_manifest=manifest)), [])


class BaseFormatCheckerTest(unittest.TestCase):
    """Direct tests for k8s_format_checker format functions."""

    def test_int32_valid(self):
        from kubernator.plugins.k8s_schema.base import check_int32
        self.assertTrue(check_int32(100))

    def test_int32_none(self):
        from kubernator.plugins.k8s_schema.base import check_int32
        self.assertFalse(check_int32(None))

    def test_int64_valid(self):
        from kubernator.plugins.k8s_schema.base import check_int64
        self.assertTrue(check_int64(2**40))

    def test_float_valid(self):
        from kubernator.plugins.k8s_schema.base import check_float
        self.assertTrue(check_float(1.5))

    def test_double_valid(self):
        from kubernator.plugins.k8s_schema.base import check_double
        self.assertTrue(check_double(1.5e100))

    def test_byte_valid(self):
        from kubernator.plugins.k8s_schema.base import check_byte
        self.assertTrue(check_byte("SGVsbG8="))

    def test_byte_invalid(self):
        from kubernator.plugins.k8s_schema.base import check_byte
        with self.assertRaises(ValueError):
            check_byte("!!!invalid!!!")

    def test_int_or_string_int(self):
        from kubernator.plugins.k8s_schema.base import check_int_or_string
        self.assertTrue(check_int_or_string(42))

    def test_int_or_string_string(self):
        from kubernator.plugins.k8s_schema.base import check_int_or_string
        self.assertTrue(check_int_or_string("hello"))

    def test_is_integer_rejects_bool(self):
        from kubernator.plugins.k8s_schema.base import is_integer
        self.assertFalse(is_integer(True))
        self.assertTrue(is_integer(42))


class ExtractGVKKeysTest(unittest.TestCase):
    def test_single_dict(self):
        from kubernator.plugins.k8s_schema.base import extract_gvk_keys
        obj = {"x-kubernetes-group-version-kind":
               {"group": "", "version": "v1", "kind": "ConfigMap"}}
        keys = list(extract_gvk_keys(obj))
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0], K8SResourceDefKey("", "v1", "ConfigMap"))

    def test_list_of_dicts(self):
        from kubernator.plugins.k8s_schema.base import extract_gvk_keys
        obj = {"x-kubernetes-group-version-kind": [
            {"group": "", "version": "v1", "kind": "ConfigMap"},
            {"group": "apps", "version": "v1", "kind": "Deployment"},
        ]}
        keys = list(extract_gvk_keys(obj))
        self.assertEqual(len(keys), 2)

    def test_missing_field(self):
        from kubernator.plugins.k8s_schema.base import extract_gvk_keys
        self.assertEqual(list(extract_gvk_keys({})), [])


class IterManifestErrorsTest(unittest.TestCase):
    def test_minimal_schema_rejects_missing_kind(self):
        v = _make_validator()
        errs = list(v.iter_manifest_errors({"apiVersion": "v1"}))
        self.assertTrue(errs)

    def test_unknown_gvk_yields_error(self):
        v = _make_validator()
        errs = list(v.iter_manifest_errors(
            {"apiVersion": "v1", "kind": "NonExistent",
             "metadata": {"name": "x"}}))
        self.assertEqual(len(errs), 1)
        self.assertIn("not a defined", str(errs[0].message))

    def test_valid_manifest_passes(self):
        v = _make_validator()
        errs = list(v.iter_manifest_errors(
            {"apiVersion": "v1", "kind": "ConfigMap",
             "metadata": {"name": "cm"},
             "data": {"a": "1", "b": "2"}}))
        self.assertEqual(errs, [])


class MixinDelegationTest(unittest.TestCase):
    def test_resource_definitions_property_delegates_to_validator(self):
        from kubernator.plugins.k8s_api import K8SResourcePluginMixin
        mixin = K8SResourcePluginMixin()
        mixin.validator = MagicMock()
        fake = {"k": "v"}
        mixin.validator.resource_definitions = fake
        self.assertIs(mixin.resource_definitions, fake)

    def test_get_api_versions_calls_validator(self):
        from kubernator.plugins.k8s_api import K8SResourcePluginMixin
        mixin = K8SResourcePluginMixin()
        mixin.validator = MagicMock()
        mixin.validator.api_versions.return_value = ["v1", "apps/v1"]
        self.assertEqual(mixin.get_api_versions(), ["v1", "apps/v1"])
        mixin.validator.api_versions.assert_called_once()
