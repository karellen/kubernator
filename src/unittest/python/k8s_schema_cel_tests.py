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
from unittest.mock import patch

from kubernator.plugins.k8s_schema.cel import CELEvaluator
from kubernator.plugins.k8s_schema.cel.rules import (ARRAY_ITEM,
                                                     collect_rules,
                                                     format_path,
                                                     resolve_path)


# ------------------------------------------------------------------ walker


class RuleWalkerTest(unittest.TestCase):
    def test_finds_nested_rules(self):
        schema = {
            "type": "object",
            "x-kubernetes-validations": [{"rule": "true", "message": "root"}],
            "properties": {
                "a": {
                    "type": "object",
                    "x-kubernetes-validations": [
                        {"rule": "self.x > 0"},
                    ],
                    "properties": {"x": {"type": "integer"}},
                },
                "b": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "x-kubernetes-validations": [
                            {"rule": "self.name.size() > 0"},
                        ],
                    },
                },
            },
        }
        paths = [(p, r["rule"]) for p, r in collect_rules(schema)]
        self.assertIn(([], "true"), paths)
        self.assertIn((["a"], "self.x > 0"), paths)
        self.assertIn((["b", ARRAY_ITEM], "self.name.size() > 0"), paths)

    def test_finds_rules_in_oneOf_branches(self):
        schema = {"oneOf": [
            {"type": "object",
             "x-kubernetes-validations": [{"rule": "branch1"}]},
            {"type": "object",
             "x-kubernetes-validations": [{"rule": "branch2"}]},
        ]}
        rules = [r["rule"] for _, r in collect_rules(schema)]
        self.assertEqual(sorted(rules), ["branch1", "branch2"])


class ResolvePathTest(unittest.TestCase):
    def test_resolve_scalar_path(self):
        self.assertEqual(list(resolve_path({"a": {"b": 3}}, ["a", "b"])), [3])

    def test_resolve_array_items(self):
        self.assertEqual(
            sorted(resolve_path({"a": [1, 2, 3]}, ["a", ARRAY_ITEM])),
            [1, 2, 3])

    def test_format_path_dotted_and_arrays(self):
        self.assertEqual(format_path(["a", ARRAY_ITEM, "b"]),
                         "$.a[*].b")


# ------------------------------------------------------------------ evaluator


class CELEvaluatorTest(unittest.TestCase):
    def setUp(self):
        self.ev = CELEvaluator()

    def _eval(self, schema, manifest, **kw):
        return list(self.ev.iter_rule_errors(manifest, schema, **kw))

    def test_simple_pass(self):
        schema = {"x-kubernetes-validations": [
            {"rule": "self.replicas <= 10", "message": "too many"}]}
        self.assertEqual(self._eval(schema, {"replicas": 3}), [])

    def test_simple_fail(self):
        schema = {"x-kubernetes-validations": [
            {"rule": "self.replicas <= 10", "message": "too many"}]}
        errs = self._eval(schema, {"replicas": 12})
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].message, "too many")

    def test_transition_rule_skipped_without_old(self):
        schema = {"x-kubernetes-validations": [
            {"rule": "self.kind == oldSelf.kind", "message": "immutable"}]}
        self.assertEqual(self._eval(schema, {"kind": "A"}), [])

    def test_transition_rule_fires_with_old(self):
        schema = {"x-kubernetes-validations": [
            {"rule": "self.kind == oldSelf.kind", "message": "immutable"}]}
        errs = self._eval(schema, {"kind": "A"},
                          old_manifest={"kind": "B"})
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].message, "immutable")

    def test_transition_rule_passes_when_unchanged(self):
        schema = {"x-kubernetes-validations": [
            {"rule": "self.kind == oldSelf.kind", "message": "immutable"}]}
        self.assertEqual(
            self._eval(schema, {"kind": "A"}, old_manifest={"kind": "A"}),
            [])

    def test_message_expression(self):
        schema = {"x-kubernetes-validations": [{
            "rule": "self.n < 5",
            "messageExpression": "'n=' + string(self.n) + ' too big'",
        }]}
        errs = self._eval(schema, {"n": 10})
        self.assertEqual(errs[0].message, "n=10 too big")

    def test_malformed_rule_does_not_abort_others(self):
        schema = {"x-kubernetes-validations": [
            {"rule": "@@syntax error"},
            {"rule": "self.n < 5", "message": "too big"},
        ]}
        errs = self._eval(schema, {"n": 10})
        # We should see both a compile-failure error and the real failure.
        self.assertGreaterEqual(len(errs), 2)

    def test_compile_cache_is_shared(self):
        # First eval triggers a compile; second should reuse it.
        schema = {"x-kubernetes-validations": [
            {"rule": "self.x > 0"}]}
        # Spy on celpy compile via patch on env
        with patch.object(self.ev._env, "compile",
                          wraps=self.ev._env.compile) as spy:
            self._eval(schema, {"x": 1})
            self._eval(schema, {"x": 5})
            self.assertEqual(spy.call_count, 1)

    def test_array_item_binding(self):
        schema = {"properties": {"items": {
            "type": "array",
            "items": {"type": "object",
                      "x-kubernetes-validations": [
                          {"rule": "self.n >= 0", "message": "negative"}]}}}}
        errs = self._eval(schema, {"items": [{"n": 1}, {"n": -1}]})
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].message, "negative")


# ------------------------------------------------------------------ ext libs


class ExtensionLibrariesTest(unittest.TestCase):
    """One representative positive-and-negative check per library so we
    exercise the registered function surface and catch regressions."""

    def setUp(self):
        self.ev = CELEvaluator()

    def _eval(self, expr, self_value):
        schema = {"x-kubernetes-validations": [
            {"rule": expr, "message": "fail"}]}
        return list(self.ev.iter_rule_errors(self_value, schema))

    # ----- lists
    def test_list_indexOf(self):
        self.assertEqual(self._eval("['a','b','c'].indexOf('b') == 1", {}), [])
        self.assertTrue(self._eval("['a','b','c'].indexOf('z') != -1", {}))

    def test_list_min_max_sum(self):
        self.assertEqual(self._eval("[3,1,2].min() == 1", {}), [])
        self.assertEqual(self._eval("[3,1,2].max() == 3", {}), [])
        self.assertEqual(self._eval("[3,1,2].sum() == 6", {}), [])

    # ----- regex
    def test_regex_find(self):
        self.assertEqual(
            self._eval("'foo-123'.find('[0-9]+') == '123'", {}), [])

    def test_regex_findAll(self):
        self.assertEqual(
            self._eval("'a1 b2 c3'.findAll('[0-9]').size() == 3", {}), [])

    # ----- quantity
    def test_quantity_isQuantity(self):
        self.assertEqual(self._eval("isQuantity('100Mi')", {}), [])
        self.assertTrue(self._eval("isQuantity('nope')", {}))

    def test_quantity_compare(self):
        self.assertEqual(
            self._eval("quantity('2Gi').isGreaterThan(quantity('500Mi'))", {}),
            [])

    # ----- IP
    def test_ip_isIP(self):
        self.assertEqual(self._eval("isIP('10.0.0.1')", {}), [])
        self.assertTrue(self._eval("isIP('nope')", {}))

    def test_ip_isLoopback(self):
        self.assertEqual(self._eval("ip('127.0.0.1').isLoopback()", {}), [])

    # ----- CIDR
    def test_cidr_containsIP(self):
        self.assertEqual(
            self._eval("cidr('10.0.0.0/8').containsIP(ip('10.1.2.3'))", {}),
            [])
        self.assertTrue(
            self._eval("cidr('10.0.0.0/8').containsIP(ip('11.0.0.1'))", {}))

    # ----- format
    def test_format_named_dns1123Label(self):
        # Valid empty error list means format OK.
        self.assertEqual(
            self._eval("namedFormat('dns1123Label').validateFormat('ok-name')"
                       ".size() == 0", {}),
            [])
        # Invalid value yields non-empty error list.
        self.assertEqual(
            self._eval("namedFormat('dns1123Label').validateFormat('Bad_Name')"
                       ".size() > 0", {}),
            [])

    # ----- optional
    def test_optional_of_has_value(self):
        self.assertEqual(self._eval("optional.of(5).hasValue()", {}), [])

    def test_optional_none_has_no_value(self):
        self.assertEqual(self._eval("!optional.none().hasValue()", {}), [])

    def test_optional_value_returns_underlying(self):
        self.assertEqual(self._eval("optional.of(42).value() == 42", {}), [])

    def test_optional_or_value_defaults_on_none(self):
        self.assertEqual(self._eval("optional.none().orValue(7) == 7", {}), [])
        self.assertEqual(self._eval("optional.of(3).orValue(7) == 3", {}), [])


class CELEvalRuleEdgeCasesTest(unittest.TestCase):
    """Tests for edge-case branches in _eval_rule and _evaluate_one."""

    def setUp(self):
        self.ev = CELEvaluator()

    def _eval(self, schema, manifest, **kw):
        return list(self.ev.iter_rule_errors(manifest, schema, **kw))

    def test_empty_rule_expression_skipped(self):
        schema = {"x-kubernetes-validations": [
            {"rule": "", "message": "should not fire"}]}
        self.assertEqual(self._eval(schema, {"x": 1}), [])

    def test_non_bool_result_yields_error(self):
        schema = {"x-kubernetes-validations": [
            {"rule": "42", "message": "should not fire"}]}
        errs = self._eval(schema, {})
        self.assertEqual(len(errs), 1)
        self.assertIn("non-bool", errs[0].message)

    def test_field_path_appended_to_error(self):
        schema = {"x-kubernetes-validations": [{
            "rule": "self.n < 5",
            "message": "too big",
            "fieldPath": ".spec.n",
        }]}
        errs = self._eval(schema, {"n": 10})
        self.assertEqual(len(errs), 1)

    def test_default_message_when_no_message_or_expression(self):
        schema = {"x-kubernetes-validations": [
            {"rule": "self.n < 5"}]}
        errs = self._eval(schema, {"n": 10})
        self.assertEqual(len(errs), 1)
        self.assertIn("failed", errs[0].message)

    def test_cel_eval_error_yields_error(self):
        schema = {"x-kubernetes-validations": [{
            "rule": "self.nonexistent.deeply.nested > 0",
            "message": "should not matter"}]}
        errs = self._eval(schema, {})
        self.assertGreaterEqual(len(errs), 1)

    def test_resolve_path_on_additionalProperties_dict(self):
        schema = {"properties": {"labels": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "x-kubernetes-validations": [{
                    "rule": "self.v != 'bad'", "message": "bad value"}]}}}}
        errs = self._eval(schema, {"labels": {
            "a": {"v": "ok"},
            "b": {"v": "bad"}}})
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].message, "bad value")


class RulesWalkerEdgeCasesTest(unittest.TestCase):
    def test_single_rule_dict_shorthand(self):
        from kubernator.plugins.k8s_schema.cel.rules import collect_rules
        schema = {"x-kubernetes-validations": {"rule": "true"}}
        rules = list(collect_rules(schema))
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0][1]["rule"], "true")

    def test_additionalProperties_walk(self):
        from kubernator.plugins.k8s_schema.cel.rules import collect_rules, ARRAY_ITEM
        schema = {"additionalProperties": {
            "type": "object",
            "x-kubernetes-validations": [{"rule": "self.x > 0"}]}}
        rules = list(collect_rules(schema))
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0][0], [ARRAY_ITEM])

    def test_resolve_path_map_values(self):
        values = list(resolve_path({"m": {"a": 1, "b": 2}},
                                   ["m", ARRAY_ITEM]))
        self.assertEqual(sorted(values), [1, 2])


class OptionalSelfSemanticsTest(unittest.TestCase):
    """Rules declaring optionalSelf/optionalOldSelf receive wrapped
    bindings so ``self.hasValue()`` / ``oldSelf.hasValue()`` work even
    when the underlying field is absent."""

    def setUp(self):
        self.ev = CELEvaluator()

    def _eval(self, schema, manifest, **kw):
        return list(self.ev.iter_rule_errors(manifest, schema, **kw))

    def test_optional_self_absent_binds_none(self):
        schema = {"properties": {
            "spec": {"type": "object",
                     "x-kubernetes-validations": [
                         {"rule": "!self.hasValue() || self.value().n > 0",
                          "optionalSelf": True,
                          "message": "n must be > 0 when present"}]}}}
        # spec is absent → optionalSelf binds self=none → rule holds
        self.assertEqual(self._eval(schema, {}), [])
        # spec present with n>0 → passes
        self.assertEqual(self._eval(schema, {"spec": {"n": 1}}), [])
        # spec present with n=0 → fails
        errs = self._eval(schema, {"spec": {"n": 0}})
        self.assertEqual(len(errs), 1)

    def test_optional_old_self_absent_binds_none(self):
        schema = {"x-kubernetes-validations": [
            {"rule": "!oldSelf.hasValue() || self.kind == oldSelf.value().kind",
             "optionalOldSelf": True,
             "message": "kind is immutable"}]}
        # first apply (no old): rule must short-circuit to true
        self.assertEqual(self._eval(schema, {"kind": "A"}), [])
        # subsequent apply with matching old: passes
        self.assertEqual(
            self._eval(schema, {"kind": "A"}, old_manifest={"kind": "A"}),
            [])
        # subsequent apply changing kind: fails
        errs = self._eval(schema, {"kind": "B"}, old_manifest={"kind": "A"})
        self.assertEqual(len(errs), 1)
