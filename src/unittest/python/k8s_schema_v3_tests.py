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

from kubernator.api import PropertyDict
from kubernator.plugins.k8s_api import K8SResourceDefKey
from kubernator.plugins.k8s_schema.v3 import (OpenAPIV3Validator,
                                              _api_version_to_gv_path,
                                              _gv_path_to_api_version,
                                              _owning_gv_paths)


def _doc(gvk_defs):
    """Build a minimal v3 sub-document containing the provided
    `gvk_defs` (mapping schema-name → (group, version, kind, schema))."""
    schemas = {}
    for name, (group, version, kind, extra) in gvk_defs.items():
        schema = {"type": "object",
                  "x-kubernetes-group-version-kind": [
                      {"group": group, "version": version, "kind": kind}],
                  "properties": {
                      "apiVersion": {"type": "string"},
                      "kind": {"type": "string"},
                      "metadata": {"type": "object",
                                   "properties": {"name": {"type": "string"}},
                                   "required": ["name"]},
                  },
                  "required": ["apiVersion", "kind"]}
        if extra:
            schema["properties"].update(extra.get("properties", {}))
            for k, v in extra.items():
                if k == "properties":
                    continue
                schema[k] = v
        schemas[name] = schema
    return {"components": {"schemas": schemas}, "paths": {}}


class FakeSource:
    name = "fake"

    def __init__(self, index, docs):
        self.index = dict(index)
        self.docs = dict(docs)
        self.doc_calls = 0

    def fetch_index(self):
        return self.index

    def fetch_document(self, key, locator):
        self.doc_calls += 1
        return self.docs[key]


class GVPathHelpersTest(unittest.TestCase):
    def test_gv_path_to_api_version_core(self):
        self.assertEqual(_gv_path_to_api_version("api/v1"), "v1")

    def test_gv_path_to_api_version_apis(self):
        self.assertEqual(_gv_path_to_api_version("apis/apps/v1"), "apps/v1")

    def test_api_version_to_gv_path_core(self):
        self.assertEqual(_api_version_to_gv_path("v1"), "api/v1")

    def test_api_version_to_gv_path_apis(self):
        self.assertEqual(_api_version_to_gv_path("apps/v1"), "apis/apps/v1")

    def test_owning_gv_paths_core(self):
        self.assertEqual(
            _owning_gv_paths("io.k8s.api.core.v1.ConfigMap",
                             ["api/v1", "apis/apps/v1"]),
            ["api/v1"])

    def test_owning_gv_paths_grouped(self):
        self.assertEqual(
            _owning_gv_paths("io.k8s.api.apps.v1.Deployment",
                             ["api/v1", "apis/apps/v1"]),
            ["apis/apps/v1"])

    def test_owning_gv_paths_dotted_group(self):
        self.assertEqual(
            _owning_gv_paths("io.k8s.api.apiextensions.k8s.io.v1.CustomResourceDefinition",
                             ["api/v1", "apis/apiextensions.k8s.io/v1"]),
            ["apis/apiextensions.k8s.io/v1"])

    def test_owning_gv_paths_apimachinery_probes_in_order(self):
        order = _owning_gv_paths("io.k8s.apimachinery.pkg.apis.meta.v1.ListMeta",
                                 ["api/v1", "apis/apps/v1", "apis/batch/v1"])
        self.assertEqual(order[0], "api/v1")
        self.assertEqual(sorted(order[1:]), ["apis/apps/v1", "apis/batch/v1"])


class OpenAPIV3ValidatorLazyFetchTest(unittest.TestCase):
    def _make(self):
        core_doc = _doc({
            "io.k8s.api.core.v1.ConfigMap": (
                "", "v1", "ConfigMap",
                {"properties": {
                    "data": {"type": "object",
                             "additionalProperties": {"type": "string"}}}}),
        })
        apps_doc = _doc({
            "io.k8s.api.apps.v1.Deployment": (
                "apps", "v1", "Deployment",
                {"properties": {
                    "spec": {"type": "object", "properties": {
                        "replicas": {"type": "integer"}}}}}),
        })
        source = FakeSource(
            index={"api/v1": "/openapi/v3/api/v1?hash=aaa",
                   "apis/apps/v1": "/openapi/v3/apis/apps/v1?hash=bbb"},
            docs={"api/v1": core_doc, "apis/apps/v1": apps_doc})
        ctx = PropertyDict()
        ctx.k8s = dict(server_git_version="v1.30.0")
        v = OpenAPIV3Validator(ctx, sources=[source])
        v.load()
        return v, source

    def test_load_does_not_fetch_subdocs(self):
        _, source = self._make()
        self.assertEqual(source.doc_calls, 0)

    def test_api_versions_from_index_only(self):
        v, source = self._make()
        self.assertEqual(sorted(v.api_versions()), ["apps/v1", "v1"])
        self.assertEqual(source.doc_calls, 0)

    def test_lookup_triggers_single_fetch(self):
        v, source = self._make()
        rdef = v.resource_definitions[K8SResourceDefKey("", "v1", "ConfigMap")]
        self.assertIsNotNone(rdef)
        self.assertEqual(source.doc_calls, 1)
        # Second lookup for same group doesn't re-fetch
        _ = v.resource_definitions[K8SResourceDefKey("", "v1", "ConfigMap")]
        self.assertEqual(source.doc_calls, 1)
        # Different group triggers a new fetch
        _ = v.resource_definitions[K8SResourceDefKey("apps", "v1", "Deployment")]
        self.assertEqual(source.doc_calls, 2)


class OpenAPIV3ValidatorIterErrorsTest(unittest.TestCase):
    def _with(self, extra_props):
        doc = _doc({"io.k8s.api.core.v1.Widget": (
            "", "v1", "Widget",
            {"properties": extra_props})})
        source = FakeSource({"api/v1": "/openapi/v3/api/v1?h=x"},
                            {"api/v1": doc})
        ctx = PropertyDict()
        ctx.k8s = dict(server_git_version="v1.30.0")
        v = OpenAPIV3Validator(ctx, sources=[source])
        v.load()
        rdef = v.resource_definitions[K8SResourceDefKey("", "v1", "Widget")]
        return v, rdef

    def test_int_or_string_via_format(self):
        v, rdef = self._with({
            "port": {"type": "string", "format": "int-or-string"}})
        m_int = {"apiVersion": "v1", "kind": "Widget",
                 "metadata": {"name": "w"}, "port": 8080}
        m_str = {"apiVersion": "v1", "kind": "Widget",
                 "metadata": {"name": "w"}, "port": "8080"}
        self.assertEqual(list(v.iter_errors(m_int, rdef)), [])
        self.assertEqual(list(v.iter_errors(m_str, rdef)), [])

    def test_int_or_string_via_extension(self):
        v, rdef = self._with({
            "port": {"type": "string", "x-kubernetes-int-or-string": True}})
        m_int = {"apiVersion": "v1", "kind": "Widget",
                 "metadata": {"name": "w"}, "port": 8080}
        m_str = {"apiVersion": "v1", "kind": "Widget",
                 "metadata": {"name": "w"}, "port": "8080"}
        self.assertEqual(list(v.iter_errors(m_int, rdef)), [])
        self.assertEqual(list(v.iter_errors(m_str, rdef)), [])

    def test_oneOf_rejects_mismatch(self):
        # OAS30 honors oneOf natively (unlike v2 swagger which drops it)
        v, rdef = self._with({
            "size": {
                "oneOf": [
                    {"type": "string", "enum": ["small", "medium", "large"]},
                    {"type": "integer"},
                ]}})
        bad = {"apiVersion": "v1", "kind": "Widget",
               "metadata": {"name": "w"}, "size": True}
        errs = list(v.iter_errors(bad, rdef))
        self.assertTrue(errs)


class GVPathEdgeCasesTest(unittest.TestCase):
    def test_gv_path_to_api_version_unknown_prefix(self):
        self.assertIsNone(_gv_path_to_api_version("unknown/v1"))

    def test_owning_gv_paths_no_match_falls_back_to_ordered(self):
        result = _owning_gv_paths("io.k8s.api.unknown.v1.Widget",
                                  ["api/v1", "apis/batch/v1"])
        self.assertEqual(result[0], "api/v1")
        self.assertIn("apis/batch/v1", result)


class OpenAPIV3ValidatorCrossDocRefTest(unittest.TestCase):
    def test_cross_doc_ref_triggers_fetch(self):
        core_doc = {
            "components": {"schemas": {
                "io.k8s.api.core.v1.ConfigMap": {
                    "type": "object",
                    "x-kubernetes-group-version-kind": [
                        {"group": "", "version": "v1", "kind": "ConfigMap"}],
                    "properties": {
                        "apiVersion": {"type": "string"},
                        "kind": {"type": "string"},
                        "metadata": {"type": "object",
                                     "properties": {"name": {"type": "string"}},
                                     "required": ["name"]},
                        "ref": {"$ref": "#/components/schemas/io.k8s.api.apps.v1.Deployment"},
                    },
                    "required": ["apiVersion", "kind"],
                },
            }},
            "paths": {},
        }
        apps_doc = _doc({
            "io.k8s.api.apps.v1.Deployment": (
                "apps", "v1", "Deployment", None),
        })
        source = FakeSource(
            index={"api/v1": "/v3/api/v1?h=x",
                   "apis/apps/v1": "/v3/apis/apps/v1?h=y"},
            docs={"api/v1": core_doc, "apis/apps/v1": apps_doc})
        ctx = PropertyDict()
        ctx.k8s = dict(server_git_version="v1.30.0")
        v = OpenAPIV3Validator(ctx, sources=[source])
        v.load()
        _ = v.resource_definitions[K8SResourceDefKey("", "v1", "ConfigMap")]
        self.assertEqual(source.doc_calls, 2)

    def test_populate_group_without_load_raises(self):
        ctx = PropertyDict()
        ctx.k8s = dict(server_git_version="v1.30.0")
        v = OpenAPIV3Validator(ctx, sources=[])
        v._index = {"api/v1": "loc"}
        with self.assertRaises(RuntimeError):
            v._populate_group("api/v1")

    def test_ensure_group_unknown_raises(self):
        source = FakeSource({"api/v1": "x"}, {"api/v1": _doc({})})
        ctx = PropertyDict()
        ctx.k8s = dict(server_git_version="v1.30.0")
        v = OpenAPIV3Validator(ctx, sources=[source])
        v.load()
        with self.assertRaises(KeyError):
            v._ensure_group_loaded("unknown", "v1")


class OpenAPIV3ValidatorLoadFallbackTest(unittest.TestCase):
    def test_primary_failure_falls_through_to_secondary(self):
        class Broken:
            name = "broken"

            def fetch_index(self):
                raise RuntimeError("boom")

            def fetch_document(self, *a, **k):
                raise AssertionError("should not be called")

        ok = FakeSource({"api/v1": "x"}, {"api/v1": _doc({})})
        ctx = PropertyDict()
        ctx.k8s = dict(server_git_version="v1.30.0")
        v = OpenAPIV3Validator(ctx, sources=[Broken(), ok])
        v.load()
        self.assertIs(v._active_source, ok)

    def test_all_sources_failing_raises(self):
        class Broken:
            name = "broken"

            def fetch_index(self):
                raise RuntimeError("nope")

        ctx = PropertyDict()
        ctx.k8s = dict(server_git_version="v1.30.0")
        v = OpenAPIV3Validator(ctx, sources=[Broken(), Broken()])
        with self.assertRaises(RuntimeError):
            v.load()
