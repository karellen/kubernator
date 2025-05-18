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


class Issue72Test(IntegrationTestSupport):
    def test_issue_72_helm_valid(self):
        test_dir = Path(__file__).parent / "issue_72" / "valid"

        os.environ["START_FRESH"] = "1"
        os.environ["KEEP_RUNNING"] = ""
        os.environ["K8S_VERSION"] = "1.31.5"
        os.environ["HELM_VERSION"] = "3.17.3"
        self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "dump")

    def test_issue_72_helm_invalid_oci(self):
        test_dir = Path(__file__).parent / "issue_72" / "invalid-oci"

        os.environ["START_FRESH"] = "1"
        os.environ["KEEP_RUNNING"] = ""
        os.environ["K8S_VERSION"] = "1.31.5"
        os.environ["HELM_VERSION"] = "3.17.3"
        with self.assertRaises(AssertionError):
            self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "dump")

    def test_issue_72_helm_invalid_repo(self):
        test_dir = Path(__file__).parent / "issue_72" / "invalid-repo"

        os.environ["START_FRESH"] = "1"
        os.environ["KEEP_RUNNING"] = ""
        os.environ["K8S_VERSION"] = "1.31.5"
        os.environ["HELM_VERSION"] = "3.17.3"
        with self.assertRaises(AssertionError):
            self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "dump")


if __name__ == "__main__":
    unittest.main()
