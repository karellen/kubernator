# -*- coding: utf-8 -*-
#
# Copyright 2021 © Payperless
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
