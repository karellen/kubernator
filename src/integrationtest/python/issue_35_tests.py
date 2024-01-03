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
import sys  # noqa: E402
import tempfile  # noqa: E402


class Issue35Test(IntegrationTestSupport):
    def test_issue_35(self):
        issue_dir = Path(__file__).parent / "issue_35"
        crd_dir = issue_dir / "crd"
        test_dir = issue_dir / "test"

        for k8s_version in ["1.20.15", "1.23.17", "1.25.16", "1.28.4"]:
            k8s_minor = int(k8s_version[2:4])

            for phase, validation in enumerate(("Ignore", "Warn", "Strict")):
                for warn_fatal in (True, False):
                    with self.subTest(k8s_version=k8s_version,
                                      validation=validation,
                                      warn_fatal=warn_fatal):
                        os.environ["K8S_VERSION"] = k8s_version
                        os.environ["START_FRESH"] = "1" if phase == 0 else ""
                        os.environ["KEEP_RUNNING"] = "1" if phase < 2 else ""
                        os.environ["FIELD_VALIDATION"] = validation
                        os.environ["WARN_FATAL"] = "1" if warn_fatal else ""

                        if phase == 0:
                            self.run_module_test("kubernator", "-p", str(crd_dir),
                                                 "-v", "DEBUG",
                                                 "apply", "--yes")
                            self.run_module_test("kubernator", "-p", str(test_dir),
                                                 "-v", "DEBUG",
                                                 "dump")
                        logs = None
                        try:
                            with tempfile.TemporaryDirectory() as temp_dir:
                                log_file = str(Path(temp_dir) / "log")
                                try:
                                    self.run_module_test("kubernator", "-p", str(test_dir),
                                                         "--log-format", "json",
                                                         "--log-file", log_file,
                                                         "-v", "DEBUG",
                                                         "apply")
                                    logs = self.load_json_logs(log_file)
                                except AssertionError:
                                    logs = self.load_json_logs(log_file)
                                    if ((not warn_fatal and validation == "Warn") or
                                            validation == "Ignore" or
                                            k8s_minor < 25):
                                        raise

                            validation_msg_found = False
                            for log in logs:
                                if "FAILED FIELD VALIDATION" in log["message"]:
                                    validation_msg_found = True
                                    break

                            if k8s_minor < 24 or validation == "Ignore":
                                self.assertFalse(validation_msg_found)
                            elif validation in ("Warn", "Strict"):
                                self.assertTrue(validation_msg_found)
                        finally:
                            if logs:
                                for log in logs:
                                    print(f"{log['ts']} {log['name']} {log['level']} {log['fn']}:{log['ln']} "
                                          f"{log['message']}",
                                          file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
