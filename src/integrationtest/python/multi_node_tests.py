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

import os  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402


class MultiNodeTest(IntegrationTestSupport):
    def test_multi_node(self):
        test_dir = Path(__file__).parent / "multi_node"

        os.environ["K8S_VERSION"] = self.K8S_TEST_VERSIONS[-1]

        try:
            self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")

            kubeconfig = Path.home() / ".cache/kubernator/kind/.kube/multi-node/config"
            self.assertTrue(kubeconfig.exists(),
                            f"Expected kubeconfig at {kubeconfig}")

            nodes_json = subprocess.check_output(
                ["docker", "ps", "-a",
                 "--filter", "label=io.x-k8s.kind.cluster=multi-node",
                 "--format", "{{.Labels}}"],
                text=True)
            roles = [line for line in nodes_json.splitlines() if line]
            control_planes = [r for r in roles if "io.x-k8s.kind.role=control-plane" in r]
            workers = [r for r in roles if "io.x-k8s.kind.role=worker" in r]
            self.assertEqual(len(control_planes), 3,
                             f"Expected 3 control-plane containers, got {len(control_planes)}: {roles}")
            self.assertEqual(len(workers), 2,
                             f"Expected 2 worker containers, got {len(workers)}: {roles}")
        finally:
            subprocess.run(["docker", "ps", "-a",
                            "--filter", "label=io.x-k8s.kind.cluster=multi-node",
                            "-q"],
                           check=False)
            # Best-effort teardown — not strictly required since keep_running=False
            # already docker-stopped the containers.


if __name__ == "__main__":
    unittest.main()
