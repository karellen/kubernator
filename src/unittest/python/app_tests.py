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
import tempfile
from collections import deque

from gevent.monkey import patch_all, is_anything_patched

if not is_anything_patched():
    patch_all()

import itertools
import os
import unittest
import configparser
from unittest.mock import Mock

from kubernator.api import KubernatorPlugin, ValueDict
from kubernator.app import App
from pathlib import Path


class DefaultDiscoveryTestCase(unittest.TestCase):
    def test_default_plugin_discovery(self):
        app = App(Mock())
        all_plugins = [cls for cls in KubernatorPlugin.__subclasses__() if cls.__name__ != 'App']
        expected: list[KubernatorPlugin] = []
        for plugin in all_plugins:
            expected.append(plugin())
        actual = app.discover_plugins()
        for (actual_class, expected_class) in itertools.zip_longest(actual, expected):
            self.assertEqual(type(actual_class), type(expected_class))


class SelectiveDiscoveryTestCase(unittest.TestCase):
    tmpdirname = tempfile.TemporaryDirectory()

    def setUp(self, tmpdirname=tmpdirname) -> None:
        config = configparser.ConfigParser(allow_no_value=True)
        plugins = {'  terraform': None,
                   '  kops': None,
                   '  kubernetes': None}
        config['plugins'] = plugins
        file = str(tmpdirname.name) + '/.kubernator.conf.py'
        with open(file, 'w') as configfile:
            config.write(configfile)

    def tearDown(self, tmpdirname=tmpdirname) -> None:
        tmpdirname.cleanup()

    def test_selective_plugin_discovery(self, tmpdirname=tmpdirname):
        app = App(Mock())
        expected: list[KubernatorPlugin] = []
        path = Path(tmpdirname.name)
        app.path_q: deque[tuple[ValueDict, Path]] = deque(((ValueDict(_parent=app.context), path),))
        for plugin in ['TerraformPlugin', 'KopsPlugin', 'KubernetesPlugin']:
            selected_plugin = [cls for cls in KubernatorPlugin.__subclasses__() if cls.__name__ == plugin]
            expected.append(selected_plugin[0]())
        actual = app.discover_plugins()
        for (actual_class, expected_class) in itertools.zip_longest(actual, expected):
            self.assertEqual(type(actual_class), type(expected_class))

    def test_register_selective_plugins(self, tmpdirname=tmpdirname):
        app = App(Mock())
        expected: list[KubernatorPlugin] = []
        path = Path(tmpdirname.name)
        app.path_q: deque[tuple[ValueDict, Path]] = deque(((ValueDict(_parent=app.context), path),))
        for plugin in ['TerraformPlugin', 'KopsPlugin', 'KubernetesPlugin']:
            selected_plugin = [cls for cls in KubernatorPlugin.__subclasses__() if cls.__name__ == plugin]
            expected.append(selected_plugin[0]())
        discovered_plugins = app.discover_plugins()
        for plugin in discovered_plugins:
            app.register_plugin(plugin)
        for (actual_class, expected_class) in itertools.zip_longest(app._plugins[1:], expected):
            self.assertEqual(type(actual_class), type(expected_class))
