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
import platform
import tempfile
import zipfile
from pathlib import Path
from shutil import which, rmtree
from stat import S_IWUSR

from kubernator.api import (KubernatorPlugin,
                            prepend_os_path,
                            StripNL,
                            get_golang_os,
                            sha256_file_digest,
                            get_cache_dir
                            )

logger = logging.getLogger("kubernator.awscli")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)


class AwsCliPlugin(KubernatorPlugin):
    logger = logger

    _name = "awscli"

    def __init__(self):
        self.context = None
        self.aws_dir = None
        self.aws_file = None

        super().__init__()

    def set_context(self, context):
        self.context = context

    def cmd(self, *args, output="json", region=None):
        context = self.context
        stanza = [context.awscli.aws_file, "--output", output]
        if region:
            stanza.extend(("--region", region))
        if logger.getEffectiveLevel() < logging.DEBUG:
            stanza.append("--debug")

        stanza.extend(args)
        return stanza

    def register(self):
        context = self.context

        # Use current version
        aws_file = which("aws")
        if not aws_file:
            logger.debug("`aws` cannot be found in PATH")
            # Download
            aws_url = f"https://awscli.amazonaws.com/awscli-exe-{get_golang_os()}-{platform.machine().lower()}.zip"
            aws_file_dl, cached = context.app.download_remote_file(logger, aws_url, "bin")

            aws_zip_digest = sha256_file_digest(aws_file_dl)
            awscli_cache_dir = get_cache_dir("awscli") / aws_zip_digest
            aws_file = awscli_cache_dir / "aws"

            if not aws_file.exists() or (aws_file.stat().st_mode & S_IWUSR == S_IWUSR):
                rmtree(awscli_cache_dir, ignore_errors=True)

            if not awscli_cache_dir.exists():
                awscli_cache_dir.mkdir(parents=True, exist_ok=True)

                with tempfile.TemporaryDirectory() as tmp_dir:
                    with zipfile.ZipFile(aws_file_dl) as zf:
                        zf.extractall(tmp_dir)

                    install_pkg_dir = Path(tmp_dir) / "aws"
                    install_file = install_pkg_dir / "install"
                    os.chmod(install_file, 0o500)
                    os.chmod(install_pkg_dir / "dist" / "aws", 0o500)
                    self.context.app.run([str(install_file), "-i",
                                          str(awscli_cache_dir), "-b", str(awscli_cache_dir)],
                                         stdout_logger,
                                         stderr_logger).wait()
                aws_file.chmod(0o500)

            self.aws_dir = awscli_cache_dir
            prepend_os_path(str(self.aws_dir))

        self.aws_file = str(aws_file)

        version_out: str = self.context.app.run_capturing_out([self.aws_file, "--version"],
                                                              stderr_logger)
        version = version_out.split(" ")[0].split("/")[1]
        logger.info("Found aws-cli %s in %r", version, self.aws_file)

        context.globals.awscli = dict(version=version,
                                      aws_file=self.aws_file,
                                      cmd=self.cmd
                                      )

    def __repr__(self):
        return "AWS CLI Plugin"
