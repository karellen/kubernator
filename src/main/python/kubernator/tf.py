# -*- coding: utf-8 -*-
#
# Copyright 2021 © Payperless
#

import json
import logging

from kubernator.api import KubernatorPlugin

logger = logging.getLogger("kubernator.tf")


class TerraformPlugin(KubernatorPlugin):
    logger = logger
    proc_logger = logger.getChild("terraform")

    def __init__(self):
        self.context = None

    def set_context(self, context):
        self.context = context

    def handle_init(self):
        context = self.context
        version = json.loads(context.app.run_capturing_out(["terraform", "version", "-json"],
                                                           self.proc_logger.error))["terraform_version"]
        logger.info("Found Terraform version %s", version)

        outputs = json.loads(context.app.run_capturing_out(["terraform", "output", "-json"],
                                                           self.proc_logger.error))

        context.globals.tf = dict(output={k: v["values"] for k, v in outputs.items()})

    def __repr__(self):
        return "Terraform Plugin"
