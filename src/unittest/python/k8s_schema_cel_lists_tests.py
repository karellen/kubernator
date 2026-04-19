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

from kubernator.plugins.k8s_schema.cel.extensions.lists import (
    indexOf,
    lastIndexOf,
    max,
    min,
    sum,
)


class IndexOfTest(unittest.TestCase):
    def test_found(self):
        seq = ct.ListType([ct.StringType("a"), ct.StringType("b"),
                           ct.StringType("c")])
        self.assertEqual(indexOf(seq, ct.StringType("b")), ct.IntType(1))

    def test_not_found(self):
        seq = ct.ListType([ct.StringType("a"), ct.StringType("b")])
        self.assertEqual(indexOf(seq, ct.StringType("z")), ct.IntType(-1))


class LastIndexOfTest(unittest.TestCase):
    def test_multiple_occurrences(self):
        seq = ct.ListType([ct.StringType("a"), ct.StringType("b"),
                           ct.StringType("a")])
        self.assertEqual(lastIndexOf(seq, ct.StringType("a")), ct.IntType(2))

    def test_not_found(self):
        seq = ct.ListType([ct.StringType("a"), ct.StringType("b")])
        self.assertEqual(lastIndexOf(seq, ct.StringType("z")), ct.IntType(-1))

    def test_single_occurrence(self):
        seq = ct.ListType([ct.StringType("x"), ct.StringType("y")])
        self.assertEqual(lastIndexOf(seq, ct.StringType("x")), ct.IntType(0))


class MinTest(unittest.TestCase):
    def test_integers(self):
        seq = ct.ListType([ct.IntType(3), ct.IntType(1), ct.IntType(2)])
        self.assertEqual(min(seq), ct.IntType(1))

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            min(ct.ListType())


class MaxTest(unittest.TestCase):
    def test_integers(self):
        seq = ct.ListType([ct.IntType(3), ct.IntType(1), ct.IntType(2)])
        self.assertEqual(max(seq), ct.IntType(3))

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            max(ct.ListType())


class SumTest(unittest.TestCase):
    def test_integers(self):
        seq = ct.ListType([ct.IntType(3), ct.IntType(1), ct.IntType(2)])
        self.assertEqual(sum(seq), ct.IntType(6))

    def test_empty(self):
        self.assertEqual(sum(ct.ListType()), ct.IntType(0))


if __name__ == "__main__":
    unittest.main()
