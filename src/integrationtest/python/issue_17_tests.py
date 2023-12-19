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

unittest  # noqa
# Above import must be first

from pathlib import Path  # noqa: E402
import os  # noqa: E402


class Issue17Test(IntegrationTestSupport):
    def test_issue_17(self):
        test_dir = Path(__file__).parent / "issue_17"

        for k8s_version in (self.K8S_TEST_VERSIONS[0], self.K8S_TEST_VERSIONS[-1]):
            with self.subTest(k8s_version=k8s_version):
                os.environ["K8S_VERSION"] = k8s_version

                os.environ["TEST_PHASE"] = "1"
                self.run_module_test("kubernator", "-p", str(test_dir), "apply", "--yes")

                os.environ["TEST_PHASE"] = "2"
                self.run_module_test("kubernator", "-p", str(test_dir), "apply", "--yes")


if __name__ == "__main__":
    unittest.main()
