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
"""K8s CEL extension library: list operations.

Mirrors ``k8s.io/apiserver/pkg/cel/library/lists.go`` — provides
``indexOf``, ``lastIndexOf``, ``min``, ``max``, ``sum`` as method-style
calls on lists.
"""

from __future__ import annotations

import celpy.celtypes as ct


def indexOf(seq, target):  # noqa: N802 — CEL identifier
    """``list.indexOf(item)`` — first index where item is found, ``-1`` if absent."""
    for i, v in enumerate(seq):
        if v == target:
            return ct.IntType(i)
    return ct.IntType(-1)


def lastIndexOf(seq, target):  # noqa: N802 — CEL identifier
    """``list.lastIndexOf(item)`` — last index where item is found, ``-1`` if absent."""
    last = -1
    for i, v in enumerate(seq):
        if v == target:
            last = i
    return ct.IntType(last)


def min(seq):  # noqa: A001 — CEL identifier
    """``list.min()`` — smallest item; raises if list is empty."""
    if not seq:
        raise ValueError("min() called on empty list")
    result = seq[0]
    for v in seq[1:]:
        if v < result:
            result = v
    return result


def max(seq):  # noqa: A001 — CEL identifier
    """``list.max()`` — largest item; raises if list is empty."""
    if not seq:
        raise ValueError("max() called on empty list")
    result = seq[0]
    for v in seq[1:]:
        if v > result:
            result = v
    return result


def sum(seq):  # noqa: A001 — CEL identifier
    """``list.sum()`` — sum of items; ``0`` for empty list."""
    if not seq:
        return ct.IntType(0)
    total = seq[0]
    for v in seq[1:]:
        total = total + v
    return total


__all__ = ["indexOf", "lastIndexOf", "min", "max", "sum"]
