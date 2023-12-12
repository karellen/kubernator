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

from kubernator.api import PropertyDict

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


class PropertyDictTestcase(unittest.TestCase):
    def test_property_dict_child_override_works(self):
        p = PropertyDict()
        p.value = [1]
        p1 = PropertyDict(_parent=p)

        self.assertEqual(len(p.value), 1)
        self.assertEqual(p.value[0], 1)
        self.assertEqual(len(p1.value), 1)
        self.assertEqual(p1.value[0], 1)

        p1.value.append(2)

        self.assertEqual(len(p.value), 1)
        self.assertEqual(p.value[0], 1)
        self.assertEqual(len(p1.value), 2)
        self.assertEqual(p1.value[0], 1)
        self.assertEqual(p1.value[1], 2)

    def test_property_dict_parent_mutation_independent(self):
        p = PropertyDict()
        p.value = [1]
        p1 = PropertyDict(_parent=p)

        self.assertEqual(len(p.value), 1)
        self.assertEqual(p.value[0], 1)
        self.assertEqual(len(p1.value), 1)
        self.assertEqual(p1.value[0], 1)

        p1.value.append(2)

        self.assertEqual(len(p.value), 1)
        self.assertEqual(p.value[0], 1)
        self.assertEqual(len(p1.value), 2)
        self.assertEqual(p1.value[0], 1)
        self.assertEqual(p1.value[1], 2)

        p.value.append(3)

        self.assertEqual(len(p.value), 2)
        self.assertEqual(p.value[0], 1)
        self.assertEqual(p.value[1], 3)
        self.assertEqual(len(p1.value), 2)
        self.assertEqual(p1.value[0], 1)
        self.assertEqual(p1.value[1], 2)
