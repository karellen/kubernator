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
import re
from tempfile import NamedTemporaryFile

from test_support import IntegrationTestSupport, unittest

unittest  # noqa
# Above import must be first

from pathlib import Path  # noqa: E402
import os  # noqa: E402


class HelmLatestVersionCheckTest(IntegrationTestSupport):
    def test_helm_latest_version_check(self):
        test_dir = Path(__file__).parent / "helm_latest_version_check"

        for k8s_version in (self.K8S_TEST_VERSIONS[-1],):
            os.environ["K8S_VERSION"] = k8s_version
            try:
                with NamedTemporaryFile(delete=False) as log_f:
                    self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE",
                                         "--log-format", "json",
                                         "--log-file", log_f.name)

                found_log_line = False
                with open(log_f.name, "rt") as f:
                    for line in f:
                        log_line = json.loads(line)
                        if (log_line["name"] == "kubernator.helm" and
                                re.match(r"Chart grafana is version [a-zA-Z\d.]+ "
                                         r"while the latest is [a-zA-Z\d.]+", log_line["message"])):
                            found_log_line = True
                            break
                self.assertTrue(found_log_line)
            finally:
                os.unlink(log_f.name)


if __name__ == "__main__":
    unittest.main()
