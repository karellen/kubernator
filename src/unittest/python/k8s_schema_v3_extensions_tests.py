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

from kubernator.plugins.k8s_schema.base import k8s_format_checker
from kubernator.plugins.k8s_schema.v3 import V3ValidatorCls


def _run(schema, instance):
    return list(V3ValidatorCls(schema,
                               format_checker=k8s_format_checker).iter_errors(instance))


class ListTypeAtomicTest(unittest.TestCase):
    SCHEMA = {"type": "array", "x-kubernetes-list-type": "atomic",
              "items": {"type": "string"}}

    def test_atomic_allows_duplicates(self):
        self.assertEqual(_run(self.SCHEMA, ["a", "a", "b"]), [])

    def test_atomic_allows_diverse_items(self):
        self.assertEqual(_run(self.SCHEMA, ["one", "two"]), [])


class ListTypeSetTest(unittest.TestCase):
    SCALAR = {"type": "array", "x-kubernetes-list-type": "set",
              "items": {"type": "string"}}
    OBJECT = {"type": "array", "x-kubernetes-list-type": "set",
              "items": {"type": "object"}}

    def test_set_rejects_duplicate_scalars(self):
        errs = _run(self.SCALAR, ["a", "b", "a"])
        self.assertTrue(errs)
        self.assertTrue(any("duplicates" in str(e.message) for e in errs))

    def test_set_rejects_deep_equal_objects(self):
        errs = _run(self.OBJECT, [{"x": 1, "y": 2}, {"y": 2, "x": 1}])
        self.assertTrue(errs)

    def test_set_passes_distinct_items(self):
        self.assertEqual(_run(self.SCALAR, ["a", "b"]), [])


class ListTypeMapTest(unittest.TestCase):
    SINGLE_KEY = {
        "type": "array",
        "x-kubernetes-list-type": "map",
        "x-kubernetes-list-map-keys": ["name"],
        "items": {"type": "object",
                  "properties": {"name": {"type": "string"},
                                 "value": {"type": "string"}}},
    }
    COMPOSITE_KEY = {
        "type": "array",
        "x-kubernetes-list-type": "map",
        "x-kubernetes-list-map-keys": ["protocol", "port"],
        "items": {"type": "object"},
    }

    def test_map_rejects_duplicate_single_key(self):
        errs = _run(self.SINGLE_KEY, [
            {"name": "a", "value": "1"},
            {"name": "a", "value": "2"},
        ])
        self.assertTrue(errs)

    def test_map_rejects_duplicate_composite_key(self):
        errs = _run(self.COMPOSITE_KEY, [
            {"protocol": "TCP", "port": 80},
            {"protocol": "TCP", "port": 80},
        ])
        self.assertTrue(errs)

    def test_map_rejects_missing_key(self):
        errs = _run(self.SINGLE_KEY, [{"value": "x"}, {"name": "b"}])
        self.assertTrue(errs)
        self.assertTrue(any("missing" in str(e.message) for e in errs))

    def test_map_passes_distinct_composite_keys(self):
        self.assertEqual(_run(self.COMPOSITE_KEY, [
            {"protocol": "TCP", "port": 80},
            {"protocol": "UDP", "port": 80},
        ]), [])


class PreserveUnknownFieldsTest(unittest.TestCase):
    SCHEMA_STRICT = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"known": {"type": "string"}},
    }
    SCHEMA_PRESERVE = {
        "type": "object",
        "additionalProperties": False,
        "x-kubernetes-preserve-unknown-fields": True,
        "properties": {"known": {"type": "string"}},
    }

    def test_strict_rejects_unknown(self):
        self.assertTrue(_run(self.SCHEMA_STRICT, {"known": "x", "extra": 1}))

    def test_preserve_allows_unknown(self):
        self.assertEqual(_run(self.SCHEMA_PRESERVE,
                              {"known": "x", "extra": 1}), [])


class IntOrStringTest(unittest.TestCase):
    """Test the type_validator int-or-string logic directly."""

    def test_null_instance_passes(self):
        schema = {"type": "string", "x-kubernetes-int-or-string": True}
        self.assertEqual(_run(schema, None), [])

    def test_bool_rejected_for_int_or_string(self):
        schema = {"type": "string", "x-kubernetes-int-or-string": True}
        errs = _run(schema, True)
        self.assertTrue(errs)

    def test_plain_type_mismatch(self):
        schema = {"type": "integer"}
        errs = _run(schema, "notanint")
        self.assertTrue(errs)


class ListTypeEdgeCasesTest(unittest.TestCase):
    def test_list_type_on_non_list_skips_list_check(self):
        from kubernator.plugins.k8s_schema.v3 import list_type_validator
        errs = list(list_type_validator(None, "set", "not-a-list", {}))
        self.assertEqual(errs, [])

    def test_map_with_non_dict_item(self):
        schema = {"type": "array", "x-kubernetes-list-type": "map",
                  "x-kubernetes-list-map-keys": ["name"],
                  "items": {"type": "object"}}
        errs = _run(schema, [42, "notadict"])
        self.assertTrue(errs)
        self.assertTrue(any("not an object" in str(e.message) for e in errs))

    def test_map_with_no_keys_defined(self):
        schema = {"type": "array", "x-kubernetes-list-type": "map",
                  "items": {"type": "object"}}
        self.assertEqual(_run(schema, [{"a": 1}, {"a": 1}]), [])

    def test_embedded_resource_suppresses_additional_properties(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "x-kubernetes-embedded-resource": True,
            "properties": {"apiVersion": {"type": "string"},
                           "kind": {"type": "string"}},
        }
        self.assertEqual(_run(schema, {"apiVersion": "v1", "kind": "Pod",
                                       "extra": "ok"}), [])


class EmbeddedResourceTest(unittest.TestCase):
    SCHEMA = {
        "type": "object",
        "x-kubernetes-embedded-resource": True,
    }

    def test_missing_kind_rejected(self):
        errs = _run(self.SCHEMA, {"apiVersion": "v1",
                                  "metadata": {"name": "a"}})
        self.assertTrue(any("'kind'" in str(e.message) for e in errs))

    def test_missing_api_version_rejected(self):
        errs = _run(self.SCHEMA, {"kind": "Pod",
                                  "metadata": {"name": "a"}})
        self.assertTrue(any("'apiVersion'" in str(e.message) for e in errs))

    def test_malformed_name_rejected(self):
        errs = _run(self.SCHEMA, {"apiVersion": "v1", "kind": "Pod",
                                  "metadata": {"name": "Bad_Name"}})
        self.assertTrue(errs)

    def test_valid_embedded(self):
        self.assertEqual(_run(self.SCHEMA, {"apiVersion": "v1", "kind": "Pod",
                                            "metadata": {"name": "ok"}}), [])
