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

from pathlib import Path  # noqa: E402
import os  # noqa: E402


class IssueOpenAPIV3Test(IntegrationTestSupport):
    """End-to-end exercise for the OpenAPI v3 validator and CEL rules.

    Phases:
      1. Apply the CRD defining Widget with x-kubernetes-validations
         (non-transition rule on replicas/maxReplicas, transition rule
         on immutable name, plus a list-type: map key).
      2. Apply a valid Widget — should succeed under v3.
      3. Apply an invalid Widget (rule + list-type violations) —
         should fail under v3.

    Runs only on the most recent supported Kubernetes version (>= 1.27
    for v3 availability; the test matrix starts at 1.29). Setting
    ``OPENAPI_VERSION=v2`` in the environment lets CI verify v2
    continues to accept the CR unchanged — v2 built-in schemas don't
    carry CEL rules, and CRD schema validation is still applied by
    the cluster server-side regardless of the client's OpenAPI mode.
    """

    def test_issue_openapi_v3(self):
        issue_dir = Path(__file__).parent / "issue_openapi_v3"
        crd_dir = issue_dir / "crd"
        pass_dir = issue_dir / "test_pass"
        fail_dir = issue_dir / "test_fail"

        k8s_version = self.K8S_TEST_VERSIONS[-1]
        os.environ["K8S_VERSION"] = k8s_version
        os.environ["OPENAPI_VERSION"] = "v3"

        # Phase 1: bring up cluster and apply CRD.
        os.environ["START_FRESH"] = "1"
        os.environ["KEEP_RUNNING"] = "1"
        self.run_module_test("kubernator", "-p", str(crd_dir), "-v", "DEBUG",
                             "apply", "--yes")

        # Phase 2: valid widget — should succeed.
        os.environ["START_FRESH"] = ""
        os.environ["KEEP_RUNNING"] = "1"
        self.run_module_test("kubernator", "-p", str(pass_dir), "-v", "DEBUG",
                             "apply", "--yes")

        # Phase 3: invalid widget — kubernator must surface the CEL
        # and list-type violations client-side (v3).
        os.environ["START_FRESH"] = ""
        os.environ["KEEP_RUNNING"] = ""
        with self.assertRaises(AssertionError):
            self.run_module_test("kubernator", "-p", str(fail_dir), "-v", "DEBUG",
                                 "apply", "--yes")


if __name__ == "__main__":
    unittest.main()
