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
import re
import tempfile
import zipfile
from pathlib import Path
from shutil import which, copy

from kubernator.api import (KubernatorPlugin, Globs, StripNL,
                            scan_dir,
                            get_golang_os,
                            get_golang_machine,
                            prepend_os_path
                            )

logger = logging.getLogger("kubernator.terraform")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)


class TerraformPlugin(KubernatorPlugin):
    logger = logger

    _name = "terraform"

    def __init__(self):
        self.context = None
        self.tf_file = None
        self.tf_dir = None

    def set_context(self, context):
        self.context = context

    def tf_stanza(self):
        return [self.tf_file]

    def register(self, version=None):
        context = self.context

        if version:
            # Download and use specific version

            tf_url = f"https://releases.hashicorp.com/terraform/{version}/terraform_" \
                     f"{version}_{get_golang_os()}_{get_golang_machine()}.zip"
            tf_file_dl, _ = context.app.download_remote_file(logger, tf_url, "bin")
            tf_file_dl = str(tf_file_dl)
            self.tf_dir = tempfile.TemporaryDirectory()

            tf_file = str(Path(self.tf_dir.name) / "terraform")
            tf_zip = zipfile.ZipFile(tf_file_dl)
            tf_zip.extractall(self.tf_dir.name)

            copy(Path(self.tf_dir.name) / "terraform", tf_file)

            os.chmod(tf_file, 0o500)
            prepend_os_path(str(self.tf_dir))
        else:
            # Use current version
            tf_file = which("terraform")
            if not tf_file:
                raise RuntimeError("`terraform` cannot be found and no version has been specified")

            logger.debug("Found Terraform in %r", tf_file)

        self.tf_file = str(tf_file)

        version_out: str = context.app.run_capturing_out([self.tf_file, "version", "-json"],
                                                         stderr_logger)
        try:
            version = json.loads(version_out)["terraform_version"]
        except json.decoder.JSONDecodeError:
            # Probably old Terraform
            if m := re.match(r"Terraform v([0-9.]+)", version_out):
                version = m[1]
            else:
                raise RuntimeError(f"Unable to determine Terraform version: {version_out}")

        context.globals.terraform = dict(version=version,
                                         tf_file=self.tf_file,
                                         tf_stanza=self.tf_stanza,
                                         )

        logger.info("Found Terraform version %s at %s", version, self.tf_file)

    def handle_init(self):
        context = self.context
        context.terraform = dict(default_includes=Globs(["*.tf"], True),
                                 default_excludes=Globs([".*"], True),
                                 )

    def handle_before_dir(self, cwd: Path):
        context = self.context
        context.terraform.default_includes = Globs(context.terraform.default_includes)
        context.terraform.default_excludes = Globs(context.terraform.default_excludes)
        context.terraform.includes = Globs(context.terraform.default_includes)
        context.terraform.excludes = Globs(context.terraform.default_excludes)

    def handle_after_dir(self, cwd: Path):
        context = self.context
        tf = context.terraform

        tf_detected = False
        for f in scan_dir(logger, cwd, lambda d: d.is_file(), tf.excludes, tf.includes):
            p = cwd / f.name
            display_p = context.app.display_path(p)
            logger.debug("Detected Terraform file in %s", display_p)
            tf_detected = True

        if not tf_detected:
            return

        context.app.run(self.tf_stanza() + ["init", "-reconfigure", "-input=false", "-upgrade=false"],
                        stdout_logger, stderr_logger, cwd=cwd).wait()

        output = json.loads(context.app.run_capturing_out(self.tf_stanza() + ["output", "-json"],
                                                          stderr_logger, cwd=cwd))
        if not output:
            raise RuntimeError("Terraform output produced no values. Please check if Terraform is functioning.")

        if "tf" not in context:
            context.tf = {}

        for k, v in output.items():
            context.tf[k] = v["value"]

    def __repr__(self):
        return "Terraform Plugin"
