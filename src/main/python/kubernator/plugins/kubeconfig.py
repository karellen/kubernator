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
                            StripNL
                            )

logger = logging.getLogger("kubernator.kubeconfig")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)


class KubeConfigPlugin(KubernatorPlugin):
    logger = logger

    _name = "kubeconfig"

    def __init__(self):
        self.context = None
        super().__init__()

    def set_context(self, context):
        self.context = context

    def register(self,
                 kubeconfig=None):
        context = self.context

        kubeconfig = kubeconfig or os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))

        context.globals.kubeconfig = dict(set=self.set_kubeconfig,
                                          register_change_notifier=self.register_change_notifier,
                                          kubeconfig=kubeconfig,
                                          _notifiers=[]
                                          )

        self.set_kubeconfig(kubeconfig)

    def set_kubeconfig(self, kubeconfig):
        context = self.context
        context.kubeconfig.kubeconfig = kubeconfig

        for n in context.kubeconfig._notifiers:
            n()

    def register_change_notifier(self, notifier):
        context = self.context

        context.kubeconfig._notifiers.append(notifier)

    def __repr__(self):
        return "Kubeconfig Plugin"
