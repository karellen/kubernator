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
from pathlib import Path
from shutil import which

from kubernator.api import (KubernatorPlugin, Globs, StripNL,
                            scan_dir,
                            get_golang_os,
                            get_golang_machine,
                            prepend_os_path
                            )

logger = logging.getLogger("kubernator.terragrunt")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)


class TerragruntPlugin(KubernatorPlugin):
    logger = logger

    _name = "terragrunt"

    def __init__(self):
        self.context = None
        self.tg_file = None
        self.tg_dir = None

    def set_context(self, context):
        self.context = context

    def tg_stanza(self):
        return [self.tg_file]

    def register(self, version=None):
        context = self.context
        context.app.register_plugin("terraform")

        if version:
            # Download and use specific version
            tg_url = (f"https://github.com/gruntwork-io/terragrunt/releases/download/v{version}/"
                      f"terragrunt_{get_golang_os()}_{get_golang_machine()}")
            tg_file, _ = context.app.download_remote_file(logger, tg_url, "bin")
            os.chmod(tg_file, 0o500)
            prepend_os_path(str(self.tg_dir))
        else:
            # Use current version
            tg_file = which("terragrunt")
            if not tg_file:
                raise RuntimeError("`terragrunt` cannot be found and no version has been specified")

            logger.debug("Found Terragrunt in %r", tg_file)

        self.tg_file = str(tg_file)

        version_out: str = context.app.run_capturing_out([self.tg_file, "-v"], stderr_logger)
        version = version_out.split(" ")[-1][1:].strip()
        context.globals.terragrunt = dict(version=version,
                                          tg_file=self.tg_file,
                                          tg_stanza=self.tg_stanza,
                                          )

        logger.info("Found Terragrunt version %s at %s", version, self.tg_file)

    def handle_init(self):
        context = self.context
        context.terragrunt = dict(default_includes=Globs(["*.hcl"], True),
                                  default_excludes=Globs([".*"], True),
                                  )

    def handle_before_dir(self, cwd: Path):
        context = self.context
        context.terragrunt.default_includes = Globs(context.terragrunt.default_includes)
        context.terragrunt.default_excludes = Globs(context.terragrunt.default_excludes)
        context.terragrunt.includes = Globs(context.terragrunt.default_includes)
        context.terragrunt.excludes = Globs(context.terragrunt.default_excludes)

    def handle_after_dir(self, cwd: Path):
        context = self.context
        tg = context.terragrunt

        tg_detected = False
        for f in scan_dir(logger, cwd, lambda d: d.is_file(), tg.excludes, tg.includes):
            p = cwd / f.name
            display_p = context.app.display_path(p)
            logger.debug("Detected Terragrunt file in %s", display_p)
            tg_detected = True

        if not tg_detected:
            return

        context.app.run(self.tg_stanza() + ["run-all", "init", "-reconfigure", "-input=false", "-upgrade=false"],
                        stdout_logger, stderr_logger, cwd=cwd).wait()

        output_json = context.app.run_capturing_out(self.tg_stanza() + ["run-all", "output", "-json"],
                                                    stderr_logger, cwd=cwd)

        json_decoder = json.JSONDecoder()
        while output_json:
            output, index = json_decoder.raw_decode(output_json)
            if not index:
                raise RuntimeError("failed to parse JSON output by Terragrunt")

            if "tf" not in context:
                context.tf = {}

            for k, v in output.items():
                context.tf[k] = v["value"]

            output_json = output_json[index:].lstrip()

    def __repr__(self):
        return "Terragrunt Plugin"
