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
import tempfile
from pathlib import Path

from kubernator.api import (KubernatorPlugin,
                            StripNL
                            )

logger = logging.getLogger("kubernator.eks")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)


class EksPlugin(KubernatorPlugin):
    logger = logger

    _name = "eks"

    def __init__(self):
        self.context = None
        self.kubeconfig_dir = tempfile.TemporaryDirectory()
        self.name = None
        self.region = None

        super().__init__()

    def set_context(self, context):
        self.context = context

    def register(self, *, name=None, region=None):
        context = self.context

        if not name:
            raise ValueError("`name` is required")

        self.name = name
        self.region = region

        context.app.register_plugin("kubeconfig")
        context.app.register_plugin("awscli")

        context.globals.eks = dict(kubeconfig=str(Path(self.kubeconfig_dir.name) / "config")
                                   )

    def handle_init(self):
        context = self.context

        self.context.app.run(context.awscli.cmd(
            "eks", "update-kubeconfig", "--name", self.name, "--kubeconfig", context.eks.kubeconfig,
            region=self.region),
            stdout_logger,
            stderr_logger).wait()

        context.kubeconfig.set(context.eks.kubeconfig)

    def handle_shutdown(self):
        self.kubeconfig_dir.cleanup()

    def __repr__(self):
        return "EKS Plugin"
