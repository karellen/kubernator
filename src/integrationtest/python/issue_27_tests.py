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
import shutil  # noqa: E402
import tarfile  # noqa: E402
import tempfile  # noqa: E402


class Issue27Test(IntegrationTestSupport):
    def test_issue_27(self):
        src_dir = Path(__file__).parent / "issue_27"
        with tempfile.TemporaryDirectory() as test_dir:
            test_dir = Path(test_dir)
            shutil.copytree(src_dir, test_dir, dirs_exist_ok=True)
            with tarfile.open(test_dir / "git.tar.gz") as tarball:
                tarball.extractall(test_dir)
            self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE")


if __name__ == "__main__":
    unittest.main()
