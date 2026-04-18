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
"""K8s CEL optional type — ``optional.of``, ``optional.none`` + methods.

cel-python doesn't natively expose CEL's ``optional<T>``. K8s's
``x-kubernetes-validations`` rules use ``optional.of(x)``,
``optional.none()``, and the member methods ``hasValue()``, ``value()``,
``orValue(default)`` when ``optionalSelf`` / ``optionalOldSelf`` is
set. This module provides a minimal, wire-compatible port:

- An ``optional`` sentinel is bound into every activation so
  ``optional.of(x)`` parses as a method call and celpy resolves it via
  ``of(optional, x)``.
- An *optional wrapper* is represented as a ``MapType`` carrying an
  internal ``_optional`` marker plus ``_hasValue`` / ``_value`` slots.
- ``of(pkg, value)``, ``none(pkg)``, ``hasValue(opt)``, ``value(opt)``,
  and ``orValue(opt, default)`` are registered as global functions;
  celpy rewrites ``obj.method(arg)`` as ``method(obj, arg)`` so the
  method-call shape is covered.

The evaluator uses :data:`OPTIONAL_SENTINEL` in activations and
:func:`wrap` / :data:`NONE` to construct wrappers when binding ``self``
and ``oldSelf`` under optional semantics.
"""

from __future__ import annotations

from typing import Any

import celpy.celtypes as ct


# Sentinel bound into every activation as `optional`.
OPTIONAL_SENTINEL: ct.MapType = ct.MapType({"_optional_pkg": ct.BoolType(True)})


def wrap(value: Any) -> ct.MapType:
    """Construct a present-value optional wrapper (``optional.of(x)``)."""
    return ct.MapType({
        "_optional": ct.BoolType(True),
        "_hasValue": ct.BoolType(True),
        "_value": value,
    })


#: Constant empty-optional wrapper (``optional.none()``).
NONE: ct.MapType = ct.MapType({
    "_optional": ct.BoolType(True),
    "_hasValue": ct.BoolType(False),
    "_value": None,
})


# --------------------------------------------------------------------- CEL

def of(pkg, value):  # noqa: ARG001 — pkg is the `optional` sentinel
    return wrap(value)


def none(pkg):  # noqa: ARG001 — pkg is the `optional` sentinel
    return NONE


def hasValue(opt):  # noqa: N802 — CEL identifier
    return ct.BoolType(bool(opt.get("_hasValue", False)))


def value(opt):
    if not opt.get("_hasValue"):
        raise ValueError("optional.value() called on empty optional")
    return opt["_value"]


def orValue(opt, default):  # noqa: N802 — CEL identifier
    if opt.get("_hasValue"):
        return opt["_value"]
    return default


__all__ = ["of", "none", "hasValue", "value", "orValue"]
