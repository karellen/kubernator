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

import logging
import os

from kubernator.api import (KubernatorPlugin,
                            StripNL,
                            get_golang_os,
                            get_golang_machine
                            )

logger = logging.getLogger("kubernator.minikube")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)


class MinikubePlugin(KubernatorPlugin):
    logger = logger

    _name = "minikube"

    def __init__(self):
        self.context = None
        self.minikube_home_dir = None
        self.kubeconfig_dir = None

        super().__init__()

    def set_context(self, context):
        self.context = context

    def get_latest_minikube_version(self):
        context = self.context
        versions = context.app.run_capturing_out(["git", "ls-remote", "-t", "--refs",
                                                  "https://github.com/kubernetes/minikube", "v*"],
                                                 stderr_logger)

        # 06e3b0cf7999f74fc52af362b42fb21076ade64a        refs/tags/v1.9.1
        # "refs/tags/v1.9.1"
        # "1.9.1"
        # ("1","9","1")
        # (1, 9, 1)
        # sort and get latest, which is the last/highest
        # "v1.9.1"
        return (".".join(map(str, sorted(list(map(lambda v: tuple(map(int, v)),
                                                  filter(lambda v: len(v) == 3,
                                                         map(lambda line: line.split()[1][11:].split("."),
                                                             versions.splitlines(False))))))[-1])))

    def cmd(self, ):
        pass

    def register(self, minikube_version=None, k8s_version=None):
        context = self.context

        context.app.register_plugin("kubectl")

        if not minikube_version:
            minikube_version = self.get_latest_minikube_version()
            logger.info("No minikube version is specified, latest is %s", minikube_version)

        minikube_file = context.app.download_remote_file(logger,
                                                         f"https://github.com/kubernetes/minikube/releases/download/"
                                                         f"v{minikube_version}/"
                                                         f"minikube-{get_golang_os()}-{get_golang_machine()}", "bin")
        os.chmod(minikube_file, 0o500)
        version_out: str = self.context.app.run_capturing_out([minikube_file, "version", "--short"],
                                                              stderr_logger)
        version = version_out[1:]
        logger.info("Found minikube %s in %r", version, minikube_file)

        context.globals.minikube = dict(version=version,
                                        minikube_file=minikube_file,
                                        cmd=self.cmd
                                        )

    def handle_init(self):
        pass

    def handle_shutdown(self):
        pass

    def __repr__(self):
        return "AWS CLI Plugin"
