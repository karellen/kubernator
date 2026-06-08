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

import json
import logging
import os
import tempfile
import zipfile
from pathlib import Path
from shutil import which

import yaml

from kubernator.api import (KubernatorPlugin, Globs, StripNL,
                            scan_dir,
                            load_file,
                            FileType,
                            TemplateEngine,
                            get_golang_os,
                            get_golang_machine,
                            prepend_os_path,
                            )

logger = logging.getLogger("kubernator.kubeone")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)


class KubeOnePlugin(KubernatorPlugin):
    logger = logger

    _name = "kubeone"

    def __init__(self):
        self.context = None
        self.kubeone_file = None
        self.kubeone_dir = None
        self._work_dir = None
        self._manifest_path = None
        self.template_engine = TemplateEngine(logger)

        super().__init__()

    def set_context(self, context):
        self.context = context

    def stanza(self):
        stanza = [self.kubeone_file]
        if self._manifest_path:
            stanza.extend(["--manifest", str(self._manifest_path)])
        if logger.getEffectiveLevel() < logging.INFO:
            stanza.append("--verbose")
        return stanza

    def register(self, version=None):
        context = self.context

        context.app.register_plugin("kubeconfig")

        self._work_dir = tempfile.TemporaryDirectory()
        context.app.register_cleanup(self._work_dir)

        if version:
            url = (f"https://github.com/kubermatic/kubeone/releases/download/"
                   f"v{version}/kubeone_{version}_{get_golang_os()}_{get_golang_machine()}.zip")
            dl_file, _ = context.app.download_remote_file(logger, url, "bin")
            dl_file = str(dl_file)
            self.kubeone_dir = tempfile.TemporaryDirectory()
            context.app.register_cleanup(self.kubeone_dir)

            kubeone_zip = zipfile.ZipFile(dl_file)
            kubeone_zip.extractall(self.kubeone_dir.name)

            kubeone_file = Path(self.kubeone_dir.name) / "kubeone"
            if not kubeone_file.exists():
                for p in Path(self.kubeone_dir.name).rglob("kubeone"):
                    if p.is_file() and p.name == "kubeone":
                        kubeone_file = p
                        break
                else:
                    raise RuntimeError("kubeone binary not found in the downloaded archive")

            os.chmod(kubeone_file, 0o500)
            prepend_os_path(str(kubeone_file.parent))
        else:
            kubeone_file = which("kubeone")
            if not kubeone_file:
                raise RuntimeError("`kubeone` cannot be found and no version has been specified")

            logger.debug("Found KubeOne in %r", kubeone_file)

        self.kubeone_file = str(kubeone_file)

        version_out = context.app.run_capturing_out(
            [self.kubeone_file, "version"], stderr_logger)
        try:
            version = json.loads(version_out)["kubeone"]["gitVersion"].lstrip("v")
        except (json.JSONDecodeError, KeyError):
            version = version_out.strip()

        kubeconfig_path = str(Path(self._work_dir.name) / "config")

        context.globals.kubeone = dict(version=version,
                                       kubeone_file=self.kubeone_file,
                                       stanza=self.stanza,
                                       kubeconfig=kubeconfig_path,
                                       apply=self.apply,
                                       status=self.status,
                                       kubeconfig_export=self.kubeconfig_export,
                                       reset=self.reset,
                                       )

        logger.info("Found KubeOne version %s at %s", version, self.kubeone_file)

    def handle_init(self):
        context = self.context
        context.kubeone = dict(default_includes=Globs(["*.kubeone.yaml", "*.kubeone.yml"], True),
                               default_excludes=Globs([".*"], True),
                               )

    def handle_start(self):
        context = self.context
        try:
            context.k8s.default_excludes.add("*.kubeone.yaml")
            context.k8s.default_excludes.add("*.kubeone.yml")
        except AttributeError:
            pass

    def handle_before_dir(self, cwd: Path):
        context = self.context
        context.kubeone.default_includes = Globs(context.kubeone.default_includes)
        context.kubeone.default_excludes = Globs(context.kubeone.default_excludes)
        context.kubeone.includes = Globs(context.kubeone.default_includes)
        context.kubeone.excludes = Globs(context.kubeone.default_excludes)

    def handle_after_dir(self, cwd: Path):
        context = self.context
        ko = context.kubeone

        for f in scan_dir(logger, cwd, lambda d: d.is_file(), ko.excludes, ko.includes):
            p = cwd / f.name
            display_p = context.app.display_path(p)

            if self._manifest_path:
                logger.warning("Multiple KubeOne manifests found; %s overrides previous manifest", display_p)

            logger.debug("Detected KubeOne manifest in %s", display_p)

            manifests = load_file(logger, p, FileType.YAML, display_p,
                                  self.template_engine,
                                  {"ktor": context})

            manifest_tmp = Path(self._work_dir.name) / "kubeone.yaml"
            with manifest_tmp.open("w") as mf:
                for manifest in manifests:
                    if manifest:
                        yaml.dump(manifest, mf, default_flow_style=False)

            self._manifest_path = manifest_tmp

            resolved = context.app.run_capturing_out(
                self.stanza() + ["config", "dump"],
                stderr_logger)
            logger.info("Validated KubeOne manifest from %s", display_p)
            logger.debug("Resolved KubeOne manifest:\n%s", resolved)

    def _tfjson_args(self):
        context = self.context
        try:
            tf = context.tf
        except AttributeError:
            return []

        tf_data = {}
        for k in dir(tf):
            tf_data[k] = {"value": tf[k]}

        tf_json_path = Path(self._work_dir.name) / "tf.json"
        with tf_json_path.open("w") as f:
            json.dump(tf_data, f)
        return ["--tfjson", str(tf_json_path)]

    def apply(self):
        context = self.context
        if not self._manifest_path:
            raise RuntimeError("No KubeOne manifest found")

        cmd = context.app.args.command
        dry_run = context.app.args.dry_run

        if cmd != "apply" or dry_run:
            status_msg = " (dump only)" if cmd == "dump" else " (dry run)"
            logger.info("Would run kubeone apply%s", status_msg)
        else:
            apply_cmd = self.stanza() + self._tfjson_args() + ["apply", "--auto-approve"]
            context.app.run(apply_cmd, stdout_logger, stderr_logger).wait()
            self.kubeconfig_export()

    def kubeconfig_export(self):
        context = self.context
        if not self._manifest_path:
            raise RuntimeError("No KubeOne manifest found")

        kubeconfig_out = context.app.run_capturing_out(
            self.stanza() + self._tfjson_args() + ["kubeconfig"],
            stderr_logger)

        kubeconfig_path = context.kubeone.kubeconfig
        with open(kubeconfig_path, "w") as f:
            f.write(kubeconfig_out)

        context.kubeconfig.set(kubeconfig_path)
        logger.info("Exported kubeconfig to %s", kubeconfig_path)

    def status(self):
        context = self.context
        if not self._manifest_path:
            raise RuntimeError("No KubeOne manifest found")

        context.app.run(
            self.stanza() + self._tfjson_args() + ["status"],
            stdout_logger, stderr_logger).wait()

    def reset(self):
        context = self.context
        if not self._manifest_path:
            raise RuntimeError("No KubeOne manifest found")

        cmd = context.app.args.command
        dry_run = context.app.args.dry_run

        if cmd != "apply" or dry_run:
            status_msg = " (dump only)" if cmd == "dump" else " (dry run)"
            logger.info("Would run kubeone reset%s", status_msg)
        else:
            reset_cmd = self.stanza() + self._tfjson_args() + ["reset", "--auto-approve"]
            context.app.run(reset_cmd, stdout_logger, stderr_logger).wait()

    def __repr__(self):
        return "KubeOne Plugin"
