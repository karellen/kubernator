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
from decimal import Decimal

import celpy.celtypes as ct

from kubernator.plugins.k8s_schema.cel.extensions.quantity import (
    _Quantity,
    _parse,
    add,
    asApproximateFloat,
    asInteger,
    compareTo,
    isGreaterThan,
    isInteger,
    isLessThan,
    isQuantity,
    quantity,
    sign,
    sub,
)


class ParseTest(unittest.TestCase):
    def test_plain_integer(self):
        q = _parse("100")
        self.assertEqual(q.value, Decimal("100"))

    def test_decimal_with_fraction(self):
        q = _parse("1.5")
        self.assertEqual(q.value, Decimal("1.5"))

    def test_si_suffix_milli(self):
        q = _parse("500m")
        self.assertEqual(q.value, Decimal("0.5"))

    def test_si_suffix_kilo(self):
        q = _parse("2k")
        self.assertEqual(q.value, Decimal("2000"))

    def test_binary_suffix_mi(self):
        q = _parse("100Mi")
        self.assertEqual(q.value, Decimal(100) * Decimal(2) ** 20)

    def test_binary_suffix_gi(self):
        q = _parse("2Gi")
        self.assertEqual(q.value, Decimal(2) * Decimal(2) ** 30)

    def test_exponent(self):
        q = _parse("1e3")
        self.assertEqual(q.value, Decimal("1000"))

    def test_negative(self):
        q = _parse("-500m")
        self.assertEqual(q.value, Decimal("-0.5"))

    def test_leading_dot(self):
        q = _parse(".5")
        self.assertEqual(q.value, Decimal("0.5"))

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            _parse("notaquantity")

    def test_repr(self):
        q = _Quantity(Decimal("100"), "Mi")
        self.assertIn("100", repr(q))
        self.assertIn("Mi", repr(q))


class QuantityFunctionTest(unittest.TestCase):
    def test_from_string(self):
        q = quantity(ct.StringType("100Mi"))
        self.assertIn("_quantity", q)

    def test_passthrough_already_wrapped(self):
        q1 = quantity(ct.StringType("100Mi"))
        q2 = quantity(q1)
        self.assertIs(q1, q2)


class IsQuantityTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(isQuantity(ct.StringType("100Mi")), ct.BoolType(True))
        self.assertEqual(isQuantity(ct.StringType("500m")), ct.BoolType(True))

    def test_invalid(self):
        self.assertEqual(isQuantity(ct.StringType("nope")), ct.BoolType(False))


class ArithmeticTest(unittest.TestCase):
    def _q(self, s):
        return quantity(ct.StringType(s))

    def test_add(self):
        result = add(self._q("100"), self._q("200"))
        self.assertEqual(Decimal(str(result["value"])), Decimal("300"))

    def test_sub(self):
        result = sub(self._q("300"), self._q("100"))
        self.assertEqual(Decimal(str(result["value"])), Decimal("200"))

    def test_isLessThan(self):
        self.assertEqual(isLessThan(self._q("100"), self._q("200")),
                         ct.BoolType(True))
        self.assertEqual(isLessThan(self._q("200"), self._q("100")),
                         ct.BoolType(False))

    def test_isGreaterThan(self):
        self.assertEqual(isGreaterThan(self._q("200"), self._q("100")),
                         ct.BoolType(True))
        self.assertEqual(isGreaterThan(self._q("100"), self._q("200")),
                         ct.BoolType(False))

    def test_compareTo(self):
        self.assertEqual(compareTo(self._q("100"), self._q("200")),
                         ct.IntType(-1))
        self.assertEqual(compareTo(self._q("200"), self._q("100")),
                         ct.IntType(1))
        self.assertEqual(compareTo(self._q("100"), self._q("100")),
                         ct.IntType(0))


class ConversionTest(unittest.TestCase):
    def _q(self, s):
        return quantity(ct.StringType(s))

    def test_asInteger(self):
        self.assertEqual(asInteger(self._q("42")), ct.IntType(42))

    def test_asInteger_overflow(self):
        huge = quantity(ct.StringType("1E30"))
        with self.assertRaises(OverflowError):
            asInteger(huge)

    def test_asApproximateFloat(self):
        result = asApproximateFloat(self._q("1.5"))
        self.assertEqual(result, ct.DoubleType(1.5))

    def test_isInteger_true(self):
        self.assertEqual(isInteger(self._q("42")), ct.BoolType(True))

    def test_isInteger_false(self):
        self.assertEqual(isInteger(self._q("1.5")), ct.BoolType(False))


class SignTest(unittest.TestCase):
    def _q(self, s):
        return quantity(ct.StringType(s))

    def test_positive(self):
        self.assertEqual(sign(self._q("100")), ct.IntType(1))

    def test_negative(self):
        self.assertEqual(sign(self._q("-100")), ct.IntType(-1))

    def test_zero(self):
        self.assertEqual(sign(self._q("0")), ct.IntType(0))


if __name__ == "__main__":
    unittest.main()
