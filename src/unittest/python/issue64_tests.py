# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2024 Karellen, Inc.
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
from kubernator.plugins.k8s import normalize_pkg_version


class Issue64Testcase(unittest.TestCase):
    def test_issue64(self):
        self.assertEqual((1, 2, 3), normalize_pkg_version("1.2.3"))
        self.assertEqual((1, 2, 3), normalize_pkg_version("1.2.3a1"))
