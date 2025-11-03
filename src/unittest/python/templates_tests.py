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

import unittest
import json
import textwrap
import yaml

from unittest.mock import Mock

from kubernator.api import TemplateEngine

JSON_DOC = json.dumps(json.loads("""
    {
        "annotations": {
            "list": [
                {
                    "builtIn": 1,
                    "datasource": "-- Grafana --",
                    "enable": true,
                    "hide": true,
                    "iconColor": "rgba(0, 211, 255, 1)",
                    "name": "Annotations & Alerts",
                    "type": "dashboard"
                }
            ]
        },
        "description": "Sealed Secrets Controller",
        "editable": true,
        "gnetId": null,
        "graphTooltip": 0,
        "id": 3,
        "iteration": 1585599163503,
        "links": [
            {
                "icon": "external link",
                "tags": [],
                "title": "GitHub",
                "tooltip": "View Project on GitHub",
                "type": "link",
                "url": "https://github.com/bitnami-labs/sealed-secrets"
            }
        ]
    }
"""), indent=2)


class TemplateTestcase(unittest.TestCase):
    def test_deep_value_resolution(self):
        te = TemplateEngine(Mock())
        t = te.from_string("{${ values.zoom }$} {${ values.foo }$}")
        self.assertEqual(t.render({"values": {"foo": "{${ values.bar }$}",
                                              "zoom": [{"x": 10}, {"y": "z"}],
                                              "bar": "{${ values.baz }$}",
                                              "baz": "baz"}}),
                         "[{'x': 10}, {'y': 'z'}] baz")

    def test_to_json_yaml_str_block(self):
        te = TemplateEngine(Mock())
        t = te.from_string(textwrap.dedent("""
        a:
            b: {${ values.obj | to_json_yaml_str_block() }$}
        """))

        data = json.loads(JSON_DOC)
        rendered = t.render({"values": {"obj": data}})
        # print(rendered)
        rendered_data = yaml.safe_load(rendered)
        self.assertEqual(rendered_data["a"]["b"], JSON_DOC)

    def test_to_yaml(self):
        te = TemplateEngine(Mock())
        t = te.from_string(textwrap.dedent("""
        a:
            b:{${ values.obj | to_yaml(8, 4) }$}
        """))

        rendered = t.render({"values": {"obj": {"x": 1, "y": 2}}})
        # print(rendered)
        self.assertEqual(rendered, textwrap.dedent("""
        a:
            b:
                x: 1
                y: 2
        """))

    def test_deep_value_resolution_to_json(self):
        te = TemplateEngine(Mock())
        t = te.from_string(textwrap.dedent("""
        a: {${ values.file_contents }$}
        """))
        rendered = t.render({"values": {"file_contents": "{${ ktor.file_contents | to_json }$}"},
                             "ktor": {"file_contents": {"a": "x", "b": "y"}}})
        self.assertEqual(rendered, '\na: {"a": "x", "b": "y"}')

    def test_deep_value_resolution_to_json_yaml_str(self):
        te = TemplateEngine(Mock())
        t = te.from_string(textwrap.dedent("""
        a: {${ values.file_contents }$}
        """))
        rendered = t.render({"values": {"file_contents": "{${ ktor.file_contents | to_json_yaml_str }$}"},
                             "ktor": {"file_contents": {"a": "x", "b": "y"}}})
        self.assertEqual(rendered, '\na: \'{"a": "x", "b": "y"}\'\n')
