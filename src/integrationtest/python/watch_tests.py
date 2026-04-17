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


class WatchTest(IntegrationTestSupport):
    def test_watch_yields_event_for_existing_resource(self):
        test_dir = Path(__file__).parent / "watch_resource"
        os.environ["K8S_VERSION"] = self.K8S_TEST_VERSIONS[-1]

        try:
            self.run_module_test("kubernator", "-p", str(test_dir), "-v", "TRACE", "apply", "--yes")

            from kubernetes import client, config
            from kubernator.plugins.k8s_api import (K8SResource, K8SResourceDef, K8SResourceDefKey)

            kubeconfig = Path.home() / ".cache/kubernator/kind/.kube/watch-resource/config"
            self.assertTrue(kubeconfig.exists(), f"Expected kubeconfig at {kubeconfig}")

            config.load_kube_config(config_file=str(kubeconfig))
            api_client = client.ApiClient()

            rdef = K8SResourceDef(K8SResourceDefKey("", "v1", "ConfigMap"),
                                  "configmap", "configmaps", True, False, None)
            rdef.populate_api(client, api_client)

            manifest = {"apiVersion": "v1", "kind": "ConfigMap",
                        "metadata": {"name": "watch-target", "namespace": "default"}}
            resource = K8SResource(manifest, rdef, source="watch_test")

            events = list(resource.watch(timeout_seconds=5))

            matching = []
            for ev in events:
                obj = ev["object"]
                name = obj["metadata"]["name"] if isinstance(obj, dict) else obj.metadata.name
                if name == "watch-target":
                    matching.append(ev)

            self.assertGreaterEqual(len(matching), 1,
                                    f"Expected watch to yield at least one event for watch-target; got {events}")
        finally:
            ids = subprocess.check_output(
                ["docker", "ps", "-aq",
                 "--filter", "label=io.x-k8s.kind.cluster=watch-resource"],
                text=True).split()
            if ids:
                subprocess.run(["docker", "rm", "-f"] + ids, check=False)


if __name__ == "__main__":
    unittest.main()
