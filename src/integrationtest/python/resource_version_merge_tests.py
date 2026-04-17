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
import json
import tempfile

from test_support import IntegrationTestSupport, unittest

unittest  # noqa
# Above import must be first

from pathlib import Path  # noqa: E402
import os  # noqa: E402


class ResourceVersionMergeTest(IntegrationTestSupport):
    def test_resource_version_merge(self):
        test_dir = Path(__file__).parent / "resource_version_merge"

        for k8s_version in (self.K8S_TEST_VERSIONS[-1],):
            os.environ["K8S_VERSION"] = k8s_version

            tmp_file_name = tempfile.mktemp()
            try:
                self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE",
                                     "-o", "json",
                                     "-f", tmp_file_name)
                with open(tmp_file_name, "r") as f:
                    result = json.load(f)

                test_ops_found = 0
                self.assertEqual(len(result), 1)
                for op in result[0]["body"]:
                    if op["op"] == "test":
                        test_ops_found += 1
                        self.assertTrue(op["path"] in ("/metadata/uid", "/metadata/resourceVersion"))
                    else:
                        self.assertEqual(op["op"], "replace")
                        self.assertEqual(op["path"], "/data/a")
                        self.assertEqual(op["value"], "c")

                self.assertEqual(test_ops_found, 2)
            finally:
                os.unlink(tmp_file_name)


if __name__ == "__main__":
    unittest.main()
