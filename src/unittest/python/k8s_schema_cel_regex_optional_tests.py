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

import celpy.celtypes as ct

from kubernator.plugins.k8s_schema.cel.extensions.regex_lib import (
    find,
    findAll,
)
from kubernator.plugins.k8s_schema.cel.extensions.optional_lib import (
    NONE,
    OPTIONAL_SENTINEL,
    hasValue,
    none,
    of,
    orValue,
    value,
    wrap,
)


# ---- regex ----

class FindTest(unittest.TestCase):
    def test_match(self):
        result = find(ct.StringType("foo-123-bar"), ct.StringType("[0-9]+"))
        self.assertEqual(result, ct.StringType("123"))

    def test_no_match(self):
        result = find(ct.StringType("foo"), ct.StringType("[0-9]+"))
        self.assertEqual(result, ct.StringType(""))


class FindAllTest(unittest.TestCase):
    def test_multiple_matches(self):
        result = findAll(ct.StringType("a1 b2 c3"), ct.StringType("[0-9]"))
        self.assertEqual(len(result), 3)

    def test_with_limit(self):
        result = findAll(ct.StringType("a1 b2 c3"), ct.StringType("[0-9]"),
                         ct.IntType(2))
        self.assertEqual(len(result), 2)

    def test_grouped_pattern(self):
        result = findAll(ct.StringType("a1 b2"), ct.StringType("([a-z])([0-9])"))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ct.StringType("a"))


# ---- optional ----

class OptionalWrapTest(unittest.TestCase):
    def test_wrap_value(self):
        w = wrap(ct.IntType(42))
        self.assertEqual(w["_hasValue"], ct.BoolType(True))
        self.assertEqual(w["_value"], ct.IntType(42))

    def test_none_constant(self):
        self.assertEqual(NONE["_hasValue"], ct.BoolType(False))


class OptionalCELFunctionsTest(unittest.TestCase):
    def test_of(self):
        result = of(OPTIONAL_SENTINEL, ct.IntType(5))
        self.assertEqual(result["_hasValue"], ct.BoolType(True))
        self.assertEqual(result["_value"], ct.IntType(5))

    def test_none_function(self):
        result = none(OPTIONAL_SENTINEL)
        self.assertIs(result, NONE)

    def test_hasValue_present(self):
        w = wrap(ct.IntType(1))
        self.assertEqual(hasValue(w), ct.BoolType(True))

    def test_hasValue_absent(self):
        self.assertEqual(hasValue(NONE), ct.BoolType(False))

    def test_value_present(self):
        w = wrap(ct.IntType(42))
        self.assertEqual(value(w), ct.IntType(42))

    def test_value_absent_raises(self):
        with self.assertRaises(ValueError):
            value(NONE)

    def test_orValue_present(self):
        w = wrap(ct.IntType(3))
        self.assertEqual(orValue(w, ct.IntType(7)), ct.IntType(3))

    def test_orValue_absent(self):
        self.assertEqual(orValue(NONE, ct.IntType(7)), ct.IntType(7))


if __name__ == "__main__":
    unittest.main()
