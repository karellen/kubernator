# -*- coding: utf-8 -*-
#
# Copyright 2021 © Payperless
#

import json
import logging
import re

from kubernator.api import KubernatorPlugin, StripNL

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
        stdout_logger = StripNL(self.proc_logger.info)
        stderr_logger = StripNL(self.proc_logger.warning)
        version_out: str = context.app.run_capturing_out(["terraform", "version", "-json"],
                                                         stderr_logger)
        try:
            version = json.loads(version_out)["terraform_version"]
        except json.decoder.JSONDecodeError:
            # Probably old Terraform
            if m := re.match(r"Terraform v([0-9.]+)", version_out):
                version = m[1]
            else:
                raise RuntimeError(f"Unable to determine Terraform version: {version_out}")

        logger.info("Found Terraform version %s", version)

        context.app.run(["terraform", "init"], stdout_logger, stderr_logger).wait()

        output = json.loads(context.app.run_capturing_out(["terraform", "output", "-json"],
                                                           stderr_logger))
        if not output:
            raise RuntimeError(f"Terraform output produced no values. Please check if Terraform is functioning.")
        context.globals.tf = {k: v["value"] for k, v in output.items()}

    def __repr__(self):
        return "Terraform Plugin"
