# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2026 Karellen, Inc.
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

from pathlib import Path  # noqa: E402
import tempfile  # noqa: E402


class JsonLogSmokeTest(IntegrationTestSupport):
    def test_json_log_format(self):
        with tempfile.TemporaryDirectory() as test_dir:
            log_file = str(Path(test_dir) / "log")
            self.run_module_test("kubernator",
                                 "--log-format", "json",
                                 "--log-file", log_file,
                                 "-v", "TRACE",
                                 "-p", test_dir,
                                 "dump")
            logs = self.load_json_logs(log_file)
            self.assertGreater(len(logs), 0)
            first = logs[0]
            self.assertIn("message", first)
            self.assertIn("ts", first)
            self.assertIn("name", first)
            self.assertIn("level", first)
            self.assertIn("fn", first)
            self.assertIn("ln", first)
            self.assertNotIn("time", first)


if __name__ == "__main__":
    unittest.main()
