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


KIND_KUBECONFIG_PATH = Path.home() / ".cache" / "kubernator" / "kind" / ".kube" / "project-v1" / "config"


class ProjectV1Test(IntegrationTestSupport):
    """Exercises the project plugin v1 end-to-end: multi-sub-project hierarchy
    → apply with cleanup=True → remove one resource → re-apply → removed
    resource gets deleted by the cleanup pass, while resources that stayed or
    moved between projects survive.
    """

    def _kubectl_configmap_names(self, namespace):
        env = dict(os.environ)
        env["KUBECONFIG"] = str(KIND_KUBECONFIG_PATH)
        out = subprocess.check_output(
            ["kubectl", "get", "configmap", "-n", namespace,
             "-o", "jsonpath={.items[*].metadata.name}"],
            env=env,
            text=True,
        )
        return set(n for n in out.split() if n)

    def _kubectl_configmap_annotation(self, namespace, name, annotation):
        env = dict(os.environ)
        env["KUBECONFIG"] = str(KIND_KUBECONFIG_PATH)
        return subprocess.check_output(
            ["kubectl", "get", "configmap", "-n", namespace, name,
             "-o", "jsonpath={.metadata.annotations." +
             annotation.replace(".", "\\.") + "}"],
            env=env,
            text=True,
        ).strip()

    def _kind_delete_cluster(self, profile):
        try:
            subprocess.run(["kind", "delete", "cluster", "--name", profile],
                           check=False, timeout=120)
        except Exception:
            pass

    def test_project_v1_cleanup_deletes_removed_resource(self):
        test_dir = Path(__file__).parent / "project_v1"
        phase1 = test_dir / "phase1"
        phase2 = test_dir / "phase2"

        for k8s_version in (self.K8S_TEST_VERSIONS[-1],):
            with self.subTest(k8s_version=k8s_version):
                os.environ["K8S_VERSION"] = k8s_version
                try:
                    # Phase 1: apply a hierarchy with three sub-project
                    # levels' worth of resources (demo, demo.a, demo.b).
                    self.run_module_test(
                        "kubernator", "-p", str(phase1), "-v", "TRACE",
                        "apply", "--yes")

                    names_after_phase1 = self._kubectl_configmap_names("demo-ns")
                    self.assertEqual(
                        names_after_phase1,
                        {"root-cfg", "a-cfg-1", "a-cfg-2", "b-cfg-1", "b-cfg-2",
                         # kube-root-ca.crt is auto-created per namespace
                         # from 1.20+.
                         "kube-root-ca.crt"},
                    )

                    # Annotations should carry the dotted project path.
                    self.assertEqual(
                        self._kubectl_configmap_annotation(
                            "demo-ns", "a-cfg-1", "kubernator.io/project"),
                        "demo.a")
                    self.assertEqual(
                        self._kubectl_configmap_annotation(
                            "demo-ns", "b-cfg-2", "kubernator.io/project"),
                        "demo.b")

                    # Phase 2: drops a-cfg-2 from the manifests.
                    self.run_module_test(
                        "kubernator", "-p", str(phase2), "-v", "TRACE",
                        "apply", "--yes")

                    names_after_phase2 = self._kubectl_configmap_names("demo-ns")
                    expected = {"root-cfg", "a-cfg-1", "b-cfg-1", "b-cfg-2",
                                "kube-root-ca.crt"}
                    self.assertEqual(
                        names_after_phase2, expected,
                        "a-cfg-2 should have been deleted by the cleanup "
                        "pass based on the prior state Secret.")
                finally:
                    self._kind_delete_cluster("project-v1")


if __name__ == "__main__":
    unittest.main()
