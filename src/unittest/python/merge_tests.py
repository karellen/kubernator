# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2021 Karellen, Inc.
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

import logging
import unittest
from kubernator.merge import extract_merge_instructions, apply_merge_instructions

TRACE = 5


def trace(self, msg, *args, **kwargs):
    """
    Log 'msg % args' with severity 'TRACE'.

    To pass exception information, use the keyword argument exc_info with
    a true value, e.g.

    logger.trace("Houston, we have a %s", "interesting problem", exc_info=1)
    """
    if self.isEnabledFor(TRACE):
        self._log(TRACE, msg, args, **kwargs)


logging.addLevelName(5, "TRACE")
logging.Logger.trace = trace

RESOURCE = "`test resource`"


class MergeTestsTestcase(unittest.TestCase):
    def test_patch_invalid_instruction(self):
        source = {"container": {"b": "y", "$patch": "merge"}}

        with self.assertRaises(ValueError):
            extract_merge_instructions(source, RESOURCE)

    def test_patch_dict_replace(self):
        source = {"container": {"b": "y", "$patch": "replace"}}
        target = {"container": {"a": "x"}}

        merge_instrs, normalized = extract_merge_instructions(source, RESOURCE)

        apply_merge_instructions(merge_instrs, normalized, target, self, RESOURCE)

        self.assertDictEqual(target, {"container": {"b": "y"}})

    def test_patch_list_replace(self):
        source = {"container": [{"b": "y"}, {"$patch": "replace"}]}
        target = {"container": [{"a": "x"}]}

        merge_instrs, normalized = extract_merge_instructions(source, RESOURCE)

        apply_merge_instructions(merge_instrs, normalized, target, self, RESOURCE)

        self.assertDictEqual(target, {"container": [{"b": "y"}]})

    def test_patch_dict_delete(self):
        source = {"container1": {"container2": {"$patch": "delete"}}}
        target = {"container1": {"container2": {"a": "x"}}}

        merge_instrs, normalized = extract_merge_instructions(source, RESOURCE)

        apply_merge_instructions(merge_instrs, normalized, target, self, RESOURCE)

        self.assertDictEqual(target, {"container1": {"container2": None}})

    def test_patch_list_delete(self):
        source = {"container1": {"container2": [{"$patch": "delete", "a": "x"}]}}
        target = {"container1": {"container2": [{"b": "y"}, {"a": "x"}]}}

        merge_instrs, normalized = extract_merge_instructions(source, RESOURCE)

        apply_merge_instructions(merge_instrs, normalized, target, self, RESOURCE)

        self.assertDictEqual(target, {"container1": {"container2": [{"b": "y"}]}})

    def test_delete_primitive_list(self):
        source = {"container1": {"container2": {"$deleteFromPrimitiveList/finalizers": ["a", "b", "d"]}}}
        target = {"container1": {"container2": {"finalizers": ["a", "b", "c"]}}}

        merge_instrs, normalized = extract_merge_instructions(source, RESOURCE)

        apply_merge_instructions(merge_instrs, normalized, target, self, RESOURCE)

        self.assertDictEqual(target, {"container1": {"container2": {"finalizers": ["c"]}}})

    def debug(self, msg, *args):
        self._log("DEBUG", msg, *args)

    def trace(self, msg, *args):
        self._log("TRACE", msg, *args)

    def warning(self, msg, *args):
        self._log("WARNING", msg, *args)

    def _log(self, lvl, msg, *args):
        print(lvl, msg % args)
