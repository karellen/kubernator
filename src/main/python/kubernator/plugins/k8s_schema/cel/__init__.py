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
"""Kubernetes CEL evaluator for ``x-kubernetes-validations`` rules.

Discovery (rule walk) is eager but cheap; compilation and evaluation
are lazy. The cache is keyed by rule expression text, so identical
rules across resources share a single compiled program.

Transition rules (those referencing ``oldSelf``) are skipped when no
``old_manifest`` is supplied, matching server behavior; rules marked
``optionalSelf`` / ``optionalOldSelf`` receive optional-wrapped
bindings via the :mod:`…cel.extensions.optional_lib` shim (cel-python
has no native ``optional<T>``).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any, Mapping, Optional

import celpy
import celpy.celtypes as ct
from celpy.evaluation import CELEvalError
from celpy.celparser import CELParseError
from jsonschema.exceptions import ValidationError

from kubernator.plugins.k8s_schema.cel.extensions import register_all
from kubernator.plugins.k8s_schema.cel.extensions import optional_lib
from kubernator.plugins.k8s_schema.cel.rules import (ARRAY_ITEM,
                                                     collect_rules,
                                                     resolve_path)

logger = logging.getLogger("kubernator.k8s_schema.cel")


_CEL_TYPES = (
    ct.BoolType, ct.BytesType, ct.DoubleType, ct.DurationType,
    ct.IntType, ct.ListType, ct.MapType, ct.StringType,
    ct.TimestampType, ct.UintType,
)

#: Sentinel bound into every activation as ``optional`` so rule text
#: like ``optional.of(x)`` resolves via method-call rewrite into
#: ``of(optional, x)``.
_OPTIONAL_BINDING = optional_lib.OPTIONAL_SENTINEL

_MISSING = object()


def _to_cel(value: Any):
    """Convert a Python/JSON value into the equivalent celtype.

    Mirrors :func:`celpy.json_to_cel` but tolerates already-converted
    values and honors ``None`` (mapped to CEL null).
    """
    if value is None:
        return None
    if isinstance(value, _CEL_TYPES):
        return value
    return celpy.json_to_cel(value)


def _optional_bind(value: Any):
    """Produce the optional-wrapped binding for ``self`` / ``oldSelf``
    when the declaring rule sets ``optionalSelf`` / ``optionalOldSelf``
    to true."""
    if value is _MISSING or value is None:
        return optional_lib.NONE
    return optional_lib.wrap(_to_cel(value))


class CELEvaluator:
    """Single-instance CEL runtime: builds one ``Environment`` and
    caches compiled programs by rule text for the lifetime of the
    evaluator (== one Kubernator run, given the validator factory)."""

    def __init__(self):
        # No annotations — ``self`` and ``oldSelf`` may bind to any
        # value (scalar, list, map). celpy's type-checker only
        # constrains when annotations are explicitly given.
        self._env = celpy.Environment()
        self._functions = register_all()
        self._program_cache: dict[str, Optional[celpy.Runner]] = {}
        self._rules_cache: dict[int, list[tuple[list[Any], dict]]] = {}

    # ------------------------------------------------------------------ caches

    def _program(self, expression: str) -> Optional[celpy.Runner]:
        if expression in self._program_cache:
            return self._program_cache[expression]
        try:
            ast = self._env.compile(expression)
            program = self._env.program(ast, functions=self._functions)
        except (CELParseError, CELEvalError, ValueError) as e:
            logger.warning("CEL rule failed to compile (%r): %s", expression, e)
            self._program_cache[expression] = None
            return None
        self._program_cache[expression] = program
        return program

    def _rules_for(self, schema: Mapping) -> list[tuple[list[Any], dict]]:
        key = id(schema)
        cached = self._rules_cache.get(key)
        if cached is None:
            cached = list(collect_rules(schema))
            self._rules_cache[key] = cached
        return cached

    # ------------------------------------------------------------------ public

    def iter_rule_errors(self,
                         manifest: Mapping,
                         schema: Mapping,
                         *,
                         old_manifest: Optional[Mapping] = None,
                         ) -> Iterator[ValidationError]:
        """Evaluate every CEL rule in *schema* against *manifest* (and,
        for transition rules, *old_manifest*). Yields one
        ``ValidationError`` per failing rule."""
        rules = self._rules_for(schema)
        if not rules:
            return

        for path, rule in rules:
            yield from self._eval_rule(path, rule, manifest, old_manifest)

    # ----------------------------------------------------------------- helpers

    def _eval_rule(self,
                   path: list[Any],
                   rule: Mapping,
                   manifest: Mapping,
                   old_manifest: Optional[Mapping]) -> Iterator[ValidationError]:
        expression = rule.get("rule")
        if not expression:
            return

        is_transition = "oldSelf" in expression
        optional_self = bool(rule.get("optionalSelf"))
        optional_old_self = bool(rule.get("optionalOldSelf"))

        values = list(resolve_path(manifest, path))
        if not values:
            if optional_self:
                values = [_MISSING]
            else:
                return

        for value in values:
            if is_transition:
                if old_manifest is None:
                    old_values: list = []
                else:
                    old_values = list(resolve_path(old_manifest, path))
                if not old_values:
                    if not optional_old_self:
                        # server-side semantics: transition rules with
                        # no prior state simply don't fire
                        continue
                    old_values = [_MISSING]
                old_value = old_values[0]
            else:
                old_value = _MISSING

            yield from self._evaluate_one(expression, rule, path,
                                          value, old_value,
                                          is_transition,
                                          optional_self,
                                          optional_old_self)

    def _evaluate_one(self,
                      expression: str,
                      rule: Mapping,
                      path: list[Any],
                      self_value: Any,
                      old_value: Any,
                      is_transition: bool,
                      optional_self: bool,
                      optional_old_self: bool) -> Iterator[ValidationError]:
        program = self._program(expression)
        if program is None:
            yield ValidationError(
                f"CEL rule could not be compiled: {expression!r}",
                validator="x-kubernetes-validations",
                validator_value=rule,
                instance=None if self_value is _MISSING else self_value,
                path=tuple(_path_str(s) for s in path),
            )
            return

        activation: dict[str, Any] = {"optional": _OPTIONAL_BINDING}
        activation["self"] = (_optional_bind(self_value) if optional_self
                              else _to_cel(self_value))
        if is_transition:
            activation["oldSelf"] = (_optional_bind(old_value) if optional_old_self
                                     else _to_cel(old_value))

        try:
            result = program.evaluate(activation)
        except CELEvalError as e:
            yield ValidationError(
                f"CEL rule {expression!r} could not be evaluated: {e}",
                validator="x-kubernetes-validations",
                validator_value=rule,
                instance=None if self_value is _MISSING else self_value,
                path=tuple(_path_str(s) for s in path),
            )
            return

        if not isinstance(result, (bool, ct.BoolType)):
            yield ValidationError(
                f"CEL rule {expression!r} returned non-bool {result!r}",
                validator="x-kubernetes-validations",
                validator_value=rule,
                instance=None if self_value is _MISSING else self_value,
                path=tuple(_path_str(s) for s in path),
            )
            return

        if bool(result):
            return

        message = self._compute_message(rule, activation)
        field_path = rule.get("fieldPath")
        full_path = list(path)
        if field_path:
            # fieldPath is a JSONPath fragment like ".spec.replicas" — append.
            full_path.append(str(field_path))

        yield ValidationError(
            message,
            validator=rule.get("reason", "x-kubernetes-validations"),
            validator_value=rule,
            instance=None if self_value is _MISSING else self_value,
            path=tuple(_path_str(s) for s in full_path),
        )

    def _compute_message(self, rule: Mapping, activation: Mapping) -> str:
        message_expr = rule.get("messageExpression")
        if message_expr:
            program = self._program(message_expr)
            if program is not None:
                try:
                    out = program.evaluate(activation)
                    return str(out)
                except CELEvalError as e:
                    logger.debug("messageExpression %r failed to evaluate: %s",
                                 message_expr, e)
        msg = rule.get("message")
        if msg:
            return str(msg)
        return f"CEL rule {rule.get('rule')!r} failed"


def _path_str(seg: Any) -> str:
    return "[*]" if seg is ARRAY_ITEM else str(seg)


__all__ = ["CELEvaluator"]
