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

import unittest
from unittest.mock import Mock

from kubernator.api import TemplateEngine


class TemplateTestcase(unittest.TestCase):
    def test_deep_value_resolution(self):
        te = TemplateEngine(Mock())
        t = te.from_string("{${ values.zoom }$} {${ values.foo }$}")
        self.assertEqual(t.render({"values": {"foo": "{${ values.bar }$}",
                                              "zoom": [{"x": 10}, {"y": "z"}],
                                              "bar": "{${ values.baz }$}",
                                              "baz": "baz"}}),
                         "[{'x': 10}, {'y': 'z'}] baz")
