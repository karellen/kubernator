# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2025 Karellen, Inc.
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
import tempfile
from pathlib import Path
from shutil import which

from kubernator.api import (KubernatorPlugin,
                            StripNL
                            )

logger = logging.getLogger("kubernator.gke")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)


class GkePlugin(KubernatorPlugin):
    logger = logger

    _name = "gke"

    def __init__(self):
        self.context = None
        self.kubeconfig_dir = tempfile.TemporaryDirectory()
        self.name = None
        self.region = None
        self.project = None
        self.gcloud_file = None

        super().__init__()

    def set_context(self, context):
        self.context = context

    def register(self, *, name=None, region=None, project=None):
        context = self.context

        if not name:
            raise ValueError("`name` is required")
        if not region:
            raise ValueError("`region` is required")
        if not project:
            raise ValueError("`project` is required")

        self.name = name
        self.region = region
        self.project = project

        # Use current version
        gcloud_file = which("gcloud")
        if not gcloud_file:
            raise RuntimeError("`gcloud` cannot be found")
        logger.debug("Found gcloud in %r", gcloud_file)
        self.gcloud_file = gcloud_file

        context.app.register_plugin("kubeconfig")

        context.globals.gke = dict(kubeconfig=str(Path(self.kubeconfig_dir.name) / "config"),
                                   name=name,
                                   region=region,
                                   project=project,
                                   gcloud_file=gcloud_file
                                   )

    def handle_init(self):
        context = self.context

        env = dict(os.environ)
        env["KUBECONFIG"] = str(context.gke.kubeconfig)
        self.context.app.run([context.gke.gcloud_file, "components", "install", "gke-gcloud-auth-plugin"],
                             stdout_logger,
                             stderr_logger).wait()
        self.context.app.run([context.gke.gcloud_file, "container", "clusters", "get-credentials",
                              context.gke.name,
                              "--region", context.gke.region,
                              "--project", context.gke.project],
                             stdout_logger,
                             stderr_logger,
                             env=env).wait()

        context.kubeconfig.set(context.gke.kubeconfig)

    def handle_shutdown(self):
        self.kubeconfig_dir.cleanup()

    def __repr__(self):
        return "GKE Plugin"
