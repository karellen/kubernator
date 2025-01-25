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
from time import sleep
from unittest import expectedFailure

from test_support import IntegrationTestSupport, unittest

unittest  # noqa
# Above import must be first

from pathlib import Path  # noqa: E402
import os  # noqa: E402


class Issue68Test(IntegrationTestSupport):
    def test_issue_68_install_operator(self):
        test_dir = Path(__file__).parent / "issue_68"

        # Install
        os.environ["START_FRESH"] = "1"
        os.environ["KEEP_RUNNING"] = ""
        os.environ["K8S_VERSION"] = "1.31.5"
        os.environ["ISTIO_VERSION"] = "1.23.4"
        self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")

    def test_issue_68_install_istioctl(self):
        test_dir = Path(__file__).parent / "issue_68"

        os.environ["START_FRESH"] = "1"
        os.environ["KEEP_RUNNING"] = ""
        os.environ["K8S_VERSION"] = "1.31.5"
        os.environ["ISTIO_VERSION"] = "1.24.2"
        self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")

    def test_issue_68_upgrade_operator_to_istioctl(self):
        test_dir = Path(__file__).parent / "issue_68"

        # Install
        os.environ["START_FRESH"] = "1"
        os.environ["KEEP_RUNNING"] = "1"
        os.environ["K8S_VERSION"] = "1.31.5"
        os.environ["ISTIO_VERSION"] = "1.23.4"
        self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")

        sleep(30)

        os.environ["START_FRESH"] = ""
        os.environ["KEEP_RUNNING"] = ""
        os.environ["K8S_VERSION"] = "1.31.5"
        os.environ["ISTIO_VERSION"] = "1.24.2"
        self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")

    def test_issue_68_upgrade_operator_to_operator(self):
        test_dir = Path(__file__).parent / "issue_68"

        # Install
        os.environ["START_FRESH"] = "1"
        os.environ["KEEP_RUNNING"] = "1"
        os.environ["K8S_VERSION"] = "1.31.5"
        os.environ["ISTIO_VERSION"] = "1.23.0"
        self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")

        sleep(30)

        os.environ["START_FRESH"] = ""
        os.environ["KEEP_RUNNING"] = ""
        os.environ["K8S_VERSION"] = "1.31.5"
        os.environ["ISTIO_VERSION"] = "1.23.4"
        self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")

    def test_issue_68_upgrade_istioctl_to_istioctl(self):
        test_dir = Path(__file__).parent / "issue_68"

        # Install
        os.environ["START_FRESH"] = "1"
        os.environ["KEEP_RUNNING"] = "1"
        os.environ["K8S_VERSION"] = "1.31.5"
        os.environ["ISTIO_VERSION"] = "1.24.0"
        self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")

        sleep(5)

        os.environ["START_FRESH"] = ""
        os.environ["KEEP_RUNNING"] = ""
        os.environ["K8S_VERSION"] = "1.31.5"
        os.environ["ISTIO_VERSION"] = "1.24.2"
        self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")

    @expectedFailure
    def test_no_downgrade(self):
        test_dir = Path(__file__).parent / "issue_68"

        # Install
        os.environ["START_FRESH"] = "1"
        os.environ["KEEP_RUNNING"] = "1"
        os.environ["K8S_VERSION"] = "1.31.5"
        os.environ["ISTIO_VERSION"] = "1.24.2"
        self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")

        sleep(5)

        os.environ["START_FRESH"] = ""
        os.environ["KEEP_RUNNING"] = ""
        os.environ["K8S_VERSION"] = "1.31.5"
        os.environ["ISTIO_VERSION"] = "1.23.4"
        self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")


if __name__ == "__main__":
    unittest.main()
