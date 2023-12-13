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
import logging
import os
import tempfile
from pathlib import Path
from shutil import which, copy

from kubernator.api import (KubernatorPlugin,
                            prepend_os_path,
                            StripNL,
                            get_golang_os,
                            get_golang_machine
                            )

logger = logging.getLogger("kubernator.kubectl")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)


class KubectlPlugin(KubernatorPlugin):
    logger = logger

    _name = "kubectl"

    def __init__(self):
        self.context = None
        self.kubectl_dir = None
        super().__init__()

    def set_context(self, context):
        self.context = context

    def kubectl_stanza(self):
        context = self.context.kubectl
        return [context.kubectl_file, f"--kubeconfig={context.kubeconfig}"]

    def register(self,
                 version=None,
                 kubeconfig=None):
        context = self.context


        kubeconfig = kubeconfig or os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))

        if version:
            # Download and use specific version
            kubectl_url = f"https://dl.k8s.io/release/v{version}/bin/" \
                          f"{get_golang_os()}/" \
                          f"{get_golang_machine()}/kubectl"
            kubectl_file_dl, _ = context.app.download_remote_file(logger, kubectl_url, "bin")
            kubectl_file_dl = str(kubectl_file_dl)
            self.kubectl_dir = tempfile.TemporaryDirectory()

            kubectl_file = str(Path(self.kubectl_dir.name) / "kubectl")
            copy(kubectl_file_dl, kubectl_file)
            os.chmod(kubectl_file, 0o500)
            prepend_os_path(str(self.kubectl_dir))
        else:
            # Use current version
            kubectl_file = which("kubectl")
            if not kubectl_file:
                raise RuntimeError("`kubectl` cannot be found and no version has been specified")

            logger.debug("Found kubectl in %r", kubectl_file)

        context.globals.kubectl = dict(version=version,
                                       kubeconfig=kubeconfig,
                                       kubectl_file=kubectl_file,
                                       kubectl_stanza=self.kubectl_stanza,
                                       test=self.test_kubectl
                                       )

        context.globals.kubectl.version = context.kubectl.test()

    def test_kubectl(self):
        version_out: str = self.context.app.run_capturing_out(self.kubectl_stanza() +
                                                              ["version", "--client=true", "-o", "json"],
                                                              stderr_logger)

        version_out_js = json.loads(version_out)
        kubectl_version = version_out_js["clientVersion"]["gitVersion"][1:]

        logger.info("Using kubectl %r version %r with stanza %r",
                    self.context.kubectl.kubectl_file, kubectl_version, self.kubectl_stanza())

        return kubectl_version

    def __repr__(self):
        return "Kubectl Plugin"
