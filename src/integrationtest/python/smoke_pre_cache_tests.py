# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2023 Karellen, Inc.
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

from test_support import IntegrationTestSupport, unittest


class PreCacheSmokeTest(IntegrationTestSupport):

    def setUp(self):
        self.run_module_test("kubernator", "--clear-k8s-cache")

    def test_precache(self):
        for k8s_version in range(19, 29):
            for disable_patches in (True, False, True):
                with self.subTest(k8s_version=k8s_version, disable_patches=disable_patches):
                    args = ["kubernator", "--pre-cache-k8s-client", str(k8s_version)]
                    if disable_patches:
                        args.append("--pre-cache-k8s-client-no-patch")
                    self.run_module_test(*args)

    @classmethod
    def tearDownClass(cls):
        cls().run_module_test("kubernator", "--clear-k8s-cache")


if __name__ == "__main__":
    unittest.main()
