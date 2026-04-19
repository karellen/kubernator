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

import logging

from kubernator.api import KubernatorPlugin

logger = logging.getLogger("kubernator.project")


class ProjectPlugin(KubernatorPlugin):
    """Switch that activates project scoping, tagging, and cleanup inside the
    k8s plugin. All behavior lives in the k8s plugin; this plugin just flips
    the switch by populating ``globals.project``."""

    _name = "project"

    def __init__(self):
        self.context = None

    def set_context(self, context):
        self.context = context

    def register(self, *, name, cleanup=False, state_namespace="kubernator-system"):
        context = self.context

        if "k8s" in context.globals:
            k8s_plugin = context.globals.k8s._k8s
            if k8s_plugin.resources:
                raise RuntimeError(
                    "project plugin must be registered before any k8s "
                    "resources are added (k8s.resources is non-empty — "
                    "register the project plugin in the pre-start script or "
                    "at the very top of the root .kubernator.py)")

        context.app.project = name
        # Root = first segment of the composed path at this context. For a
        # registration nested under a context that already carries a
        # segment, the parent's segment is the root, not ``name``.
        root = context.app.project.split(".", 1)[0]
        context.globals.project = dict(
            root=root,
            cleanup=cleanup,
            state_namespace=state_namespace,
        )
        logger.info("Project plugin registered with root project %r "
                    "(cleanup=%s, state_namespace=%r)",
                    name, cleanup, state_namespace)

    def __repr__(self):
        return "Project Plugin"
