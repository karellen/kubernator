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
import tempfile  # noqa: E402
import yaml  # noqa: E402
from pprint import pprint  # noqa: E402


class Issue48Test(IntegrationTestSupport):
    def test_issue_48(self):
        test_dir = Path(__file__).parent / "issue_48"
        test_dir_1 = test_dir / "phase1"
        test_dir_2 = test_dir / "phase2"
        with tempfile.TemporaryDirectory() as results_dir:
            results_file = Path(results_dir) / "results"
            for k8s_version in (self.K8S_TEST_VERSIONS[-1],):
                with self.subTest(k8s_version=k8s_version):
                    os.environ["K8S_VERSION"] = k8s_version

                    self.run_module_test("kubernator", "-p", str(test_dir_1), "-v", "TRACE", "apply", "--yes")
                    self.run_module_test("kubernator", "-p", str(test_dir_2),
                                         "-v", "TRACE", "-f", str(results_file), "dump")

                    with open(results_file, "rb") as f:
                        results = list(yaml.safe_load_all(f))
                        pprint(results)


if __name__ == "__main__":
    unittest.main()
