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
"""Walks an OpenAPI v3 schema collecting ``x-kubernetes-validations``
rules together with the manifest paths they apply to.

The walker yields one entry per rule:

    (manifest_path, rule_dict)

where ``manifest_path`` is a list of segments — each segment is either
a string property name or the sentinel :data:`ARRAY_ITEM` marking
descent into a list item (the actual index is supplied by the
evaluator at value lookup time). Rules attached to a schema apply to
the value at that path.

The walker does **not** compile rule expressions; compilation happens
lazily inside the evaluator on first use.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Mapping


# Sentinel for "any list item" in the dotted-path used by collect_rules.
ARRAY_ITEM = object()


def _rules_at(schema: Mapping) -> list:
    rules = schema.get("x-kubernetes-validations")
    if not rules:
        return []
    if isinstance(rules, Mapping):  # tolerate single-rule shorthand
        return [rules]
    return list(rules)


def collect_rules(schema: Mapping) -> Iterator[tuple[list[Any], dict]]:
    """Yield ``(path, rule)`` tuples for every CEL validation rule in
    *schema*. Recurses through ``properties``, ``items``,
    ``additionalProperties``, and the composition keywords
    (``allOf``/``oneOf``/``anyOf``)."""
    yield from _walk(schema, [])


def _walk(schema: Any, path: list[Any]) -> Iterator[tuple[list[Any], dict]]:
    if not isinstance(schema, Mapping):
        return

    for rule in _rules_at(schema):
        yield (list(path), rule)

    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for name, sub in properties.items():
            yield from _walk(sub, path + [name])

    items = schema.get("items")
    if isinstance(items, Mapping):
        yield from _walk(items, path + [ARRAY_ITEM])

    additional = schema.get("additionalProperties")
    if isinstance(additional, Mapping):
        # Map values: rule applies to each map value; path semantics
        # mirror an array item (the evaluator iterates).
        yield from _walk(additional, path + [ARRAY_ITEM])

    for keyword in ("allOf", "anyOf", "oneOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list):
            for branch in branches:
                yield from _walk(branch, path)


def resolve_path(value: Any, path: list[Any]) -> Iterator[Any]:
    """Yield every value reachable in *value* by descending *path*.
    For string segments, yields the named property's value; for
    :data:`ARRAY_ITEM`, yields each list element (or each map value
    when the parent is a dict — covers ``additionalProperties``)."""
    if not path:
        yield value
        return
    head, tail = path[0], path[1:]
    if head is ARRAY_ITEM:
        if isinstance(value, list):
            for item in value:
                yield from resolve_path(item, tail)
        elif isinstance(value, Mapping):
            for v in value.values():
                yield from resolve_path(v, tail)
        return
    if isinstance(value, Mapping) and head in value:
        yield from resolve_path(value[head], tail)


def format_path(path: list[Any]) -> str:
    """Render *path* as a dotted string like ``$.spec.containers[*].image``
    suitable for inclusion in error messages."""
    out = ["$"]
    for seg in path:
        if seg is ARRAY_ITEM:
            out.append("[*]")
        else:
            out.append(f".{seg}")
    return "".join(out)
