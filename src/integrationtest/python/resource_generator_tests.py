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
# Above import must be first

import os  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402


class ResourceGeneratorSeamTest(IntegrationTestSupport):
    def test_custom_generator_filters_apply_set(self):
        test_dir = Path(__file__).parent / "resource_generator"
        os.environ["K8S_VERSION"] = self.K8S_TEST_VERSIONS[-1]

        try:
            self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")

            kubeconfig = Path.home() / ".cache/kubernator/kind/.kube/resource-generator/config"
            self.assertTrue(kubeconfig.exists(), f"Expected kubeconfig at {kubeconfig}")
            env = {**os.environ, "KUBECONFIG": str(kubeconfig)}

            out = subprocess.check_output(
                ["kubectl", "get", "cm", "-n", "default", "-o", "name"],
                env=env, text=True)

            self.assertIn("configmap/cm-keep", out,
                          f"cm-keep (yielded by custom generator) should have been applied; got {out!r}")
            self.assertNotIn("configmap/cm-skip", out,
                             f"cm-skip (filtered out by custom generator) should not have been applied; got {out!r}")
        finally:
            ids = subprocess.check_output(
                ["docker", "ps", "-aq",
                 "--filter", "label=io.x-k8s.kind.cluster=resource-generator"],
                text=True).split()
            if ids:
                subprocess.run(["docker", "rm", "-f"] + ids, check=False)


if __name__ == "__main__":
    unittest.main()
