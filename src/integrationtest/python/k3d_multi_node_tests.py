# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2024 Karellen, Inc.
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


class K3dMultiNodeTest(IntegrationTestSupport):
    def test_k3d_multi_node(self):
        test_dir = Path(__file__).parent / "k3d_multi_node"

        os.environ["K8S_VERSION"] = self.K8S_TEST_VERSIONS[-1]

        try:
            self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")

            kubeconfig = Path.home() / ".cache/kubernator/k3d/.kube/k3d-multi-node/config"
            self.assertTrue(kubeconfig.exists(),
                            f"Expected kubeconfig at {kubeconfig}")

            labels = subprocess.check_output(
                ["docker", "ps", "-a",
                 "--filter", "label=k3d.cluster=k3d-multi-node",
                 "--format", "{{.Labels}}"],
                text=True)
            roles = [line for line in labels.splitlines() if line]
            servers = [r for r in roles if "k3d.role=server" in r]
            agents = [r for r in roles if "k3d.role=agent" in r]
            # k3d also spawns a `loadbalancer`-role container when servers >= 2;
            # filter explicitly so it doesn't skew the totals.
            self.assertEqual(len(servers), 3,
                             f"Expected 3 server containers, got {len(servers)}: {roles}")
            self.assertEqual(len(agents), 2,
                             f"Expected 2 agent containers, got {len(agents)}: {roles}")
        finally:
            subprocess.run(["docker", "ps", "-a",
                            "--filter", "label=k3d.cluster=k3d-multi-node",
                            "-q"],
                           check=False)
            # Best-effort teardown — not strictly required since keep_running=False
            # already stopped the cluster via `k3d cluster stop`.


if __name__ == "__main__":
    unittest.main()
