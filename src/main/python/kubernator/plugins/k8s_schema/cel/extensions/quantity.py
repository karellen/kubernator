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
"""K8s CEL extension library: resource quantities.

Mirrors ``k8s.io/apiserver/pkg/cel/library/quantity.go`` and the
underlying ``k8s.io/apimachinery/pkg/api/resource.Quantity`` parser.
"""

from __future__ import annotations

import re
from decimal import Decimal

import celpy.celtypes as ct

# SI suffixes (decimal): 10^N
_SI_DEC = {
    "n": Decimal(10) ** -9,
    "u": Decimal(10) ** -6,
    "m": Decimal(10) ** -3,
    "":  Decimal(1),
    "k": Decimal(10) ** 3,
    "M": Decimal(10) ** 6,
    "G": Decimal(10) ** 9,
    "T": Decimal(10) ** 12,
    "P": Decimal(10) ** 15,
    "E": Decimal(10) ** 18,
}

# Binary suffixes: 2^(10*N)
_SI_BIN = {
    "Ki": Decimal(2) ** 10,
    "Mi": Decimal(2) ** 20,
    "Gi": Decimal(2) ** 30,
    "Ti": Decimal(2) ** 40,
    "Pi": Decimal(2) ** 50,
    "Ei": Decimal(2) ** 60,
}

_QUANTITY_RE = re.compile(
    r"^"
    r"(?P<sign>[+-]?)"
    r"(?P<num>\d+(\.\d+)?|\.\d+)"
    r"(?P<exp>[eE][+-]?\d+)?"
    r"(?P<unit>Ei|Pi|Ti|Gi|Mi|Ki|[numkMGTPE])?"
    r"$"
)


class _Quantity:
    """In-memory representation of a parsed K8s quantity.

    The value is stored as a :class:`decimal.Decimal` for exact
    arithmetic; suffix info is preserved only to round-trip via
    ``str(q)`` (not currently used).
    """

    __slots__ = ("value", "_unit")

    def __init__(self, value: Decimal, unit: str = ""):
        self.value = value
        self._unit = unit

    def __repr__(self):
        return f"_Quantity({self.value}, {self._unit!r})"


def _parse(value: str) -> _Quantity:
    m = _QUANTITY_RE.match(value)
    if not m:
        raise ValueError(f"invalid quantity: {value!r}")
    sign = m.group("sign") or ""
    num = m.group("num")
    exp = m.group("exp") or ""
    unit = m.group("unit") or ""

    base = Decimal(f"{sign}{num}{exp}")
    if unit in _SI_BIN:
        multiplier = _SI_BIN[unit]
    elif unit in _SI_DEC:
        multiplier = _SI_DEC[unit]
    else:  # pragma: no cover — regex restricts the inputs
        raise ValueError(f"unknown quantity unit: {unit!r}")
    return _Quantity(base * multiplier, unit)


def quantity(value):
    """``quantity("100Mi")`` → quantity object."""
    if isinstance(value, ct.MapType) and "_quantity" in value:
        return value
    parsed = _parse(str(value))
    return ct.MapType({"_quantity": True, "value": ct.StringType(str(parsed.value))})


def isQuantity(value):  # noqa: N802 — CEL identifier
    """``isQuantity("100Mi")`` → bool. Also callable as method on string."""
    try:
        _parse(str(value))
        return ct.BoolType(True)
    except ValueError:
        return ct.BoolType(False)


def _value(q) -> Decimal:
    return Decimal(str(q["value"]))


def add(q1, q2):
    """``q1.add(q2)`` (or ``add(q1, q2)``) → quantity sum."""
    total = _value(q1) + _value(q2)
    return ct.MapType({"_quantity": True, "value": ct.StringType(str(total))})


def sub(q1, q2):
    total = _value(q1) - _value(q2)
    return ct.MapType({"_quantity": True, "value": ct.StringType(str(total))})


def isLessThan(q1, q2):  # noqa: N802 — CEL identifier
    return ct.BoolType(_value(q1) < _value(q2))


def isGreaterThan(q1, q2):  # noqa: N802 — CEL identifier
    return ct.BoolType(_value(q1) > _value(q2))


def compareTo(q1, q2):  # noqa: N802 — CEL identifier
    a, b = _value(q1), _value(q2)
    if a < b:
        return ct.IntType(-1)
    if a > b:
        return ct.IntType(1)
    return ct.IntType(0)


def asInteger(q):  # noqa: N802 — CEL identifier
    """``q.asInteger()`` — truncates toward zero, errors on overflow."""
    val = _value(q)
    truncated = int(val)
    if truncated.bit_length() > 63:
        raise OverflowError("quantity does not fit in int64")
    return ct.IntType(truncated)


def asApproximateFloat(q):  # noqa: N802 — CEL identifier
    return ct.DoubleType(float(_value(q)))


def isInteger(q):  # noqa: N802 — CEL identifier
    return ct.BoolType(_value(q) == _value(q).to_integral_value())


def sign(q):
    val = _value(q)
    if val > 0:
        return ct.IntType(1)
    if val < 0:
        return ct.IntType(-1)
    return ct.IntType(0)


__all__ = [
    "quantity",
    "isQuantity",
    "add",
    "sub",
    "isLessThan",
    "isGreaterThan",
    "compareTo",
    "asInteger",
    "asApproximateFloat",
    "isInteger",
    "sign",
]
