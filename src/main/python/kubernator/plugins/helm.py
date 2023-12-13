# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2021 Karellen, Inc.
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
import tarfile
import tempfile
from hashlib import sha256
from pathlib import Path
from shutil import which, copy
from typing import Sequence

import yaml
from jsonschema import Draft7Validator, draft7_format_checker

from kubernator.api import (KubernatorPlugin, Globs, StripNL,
                            scan_dir,
                            load_file,
                            FileType,
                            calling_frame_source,
                            validator_with_defaults,
                            get_golang_os,
                            get_golang_machine,
                            prepend_os_path
                            )
from kubernator.plugins.k8s_api import K8SResource
from kubernator.proc import DEVNULL

logger = logging.getLogger("kubernator.helm")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)

HELM_SCHEMA = {
    "properties": {
        "repository": {
            "type": "string",
            "description": "repository hosting the charts"
        },
        "chart": {
            "type": "string",
            "description": "chart name within the repository"
        },
        "version": {
            "type": "string",
            "description": "chart version"
        },
        "name": {
            "type": "string",
            "description": "name of the particular release"
        },
        "namespace": {
            "type": "string",
            "description": "namespace where the chart is going to be deployed"
        },
        "include-crds": {
            "type": "boolean",
            "default": True,
            "description": "generate CRDs for the helm"
        },
        "values": {
            "type": "object",
            "additionalProperties": True,
            "description": "inline Helm chart values"
        },
        "values-file": {
            "type": "string",
            "description": "reference to the file containing Helm chart values"
        }
    },
    "type": "object",
    "required": ["repository", "chart", "version", "name", "namespace"]
}

Draft7Validator.check_schema(HELM_SCHEMA)
HELM_VALIDATOR_CLS = validator_with_defaults(Draft7Validator)
HELM_VALIDATOR = HELM_VALIDATOR_CLS(HELM_SCHEMA, format_checker=draft7_format_checker)


class HelmPlugin(KubernatorPlugin):
    logger = logger

    _name = "helm"

    def __init__(self):
        self.context = None
        self.repositories = set()
        self.helm_dir = None

    def set_context(self, context):
        self.context = context

    def helm_stanza(self):
        context = self.context
        stanza = [context.helm.helm_file, f"--kubeconfig={context.kubeconfig.kubeconfig}"]
        if logger.getEffectiveLevel() < logging.INFO:
            stanza.append("--debug")
        return stanza

    def register(self, version=None):
        context = self.context
        context.app.register_plugin("kubeconfig")
        context.app.register_plugin("k8s")

        if version:
            # Download and use specific version
            helm_url = f"https://get.helm.sh/helm-v{version}-{get_golang_os()}-{get_golang_machine()}.tar.gz"
            helm_file_dl, _ = context.app.download_remote_file(logger, helm_url, "bin")
            helm_file_dl = str(helm_file_dl)
            self.helm_dir = tempfile.TemporaryDirectory()

            helm_file = str(Path(self.helm_dir.name) / "helm")
            helm_tar = tarfile.open(helm_file_dl)
            helm_tar.extractall(self.helm_dir.name)

            copy(Path(self.helm_dir.name)/f"{get_golang_os()}-{get_golang_machine()}"/"helm", helm_file)

            os.chmod(helm_file, 0o500)
            prepend_os_path(str(self.helm_dir))
        else:
            # Use current version
            helm_file = which("helm")
            if not helm_file:
                raise RuntimeError("`helm` cannot be found and no version has been specified")

            logger.debug("Found Helm in %r", helm_file)

        context.globals.helm = dict(default_includes=Globs(["*.helm.yaml", "*.helm.yml"], True),
                                    default_excludes=Globs([".*"], True),
                                    namespace_transformer=True,
                                    helm_file=helm_file,
                                    helm_stanza=self.helm_stanza,
                                    add_helm_template=self.add_helm_template,
                                    add_helm=self.add_helm,
                                    )

    def handle_init(self):
        version = self.context.app.run_capturing_out(self.helm_stanza() + ["version", "--template", "{{.Version}}"],
                                                     logger.error)
        logger.info("Found Helm version %s", version)

    def handle_start(self):
        pass

    def handle_before_dir(self, cwd: Path):
        context = self.context

        context.helm.default_includes = Globs(context.helm.default_includes)
        context.helm.default_excludes = Globs(context.helm.default_excludes)
        context.helm.includes = Globs(context.helm.default_includes)
        context.helm.excludes = Globs(context.helm.default_excludes)

        # Exclude Helm YAMLs from K8S resource loading
        context.k8s.excludes.add("*.helm.yaml")
        context.k8s.excludes.add("*.helm.yml")

    def handle_after_dir(self, cwd: Path):
        context = self.context
        helm = context.helm

        for f in scan_dir(logger, cwd, lambda d: d.is_file(), helm.excludes, helm.includes):
            p = cwd / f.name
            display_p = context.app.display_path(p)
            logger.debug("Adding Helm template from %s", display_p)

            helm_templates = load_file(logger, p, FileType.YAML, display_p)

            for helm_template in helm_templates:
                self._add_helm(helm_template, display_p)

    def add_helm_template(self, template):
        return self._add_helm(template, calling_frame_source())

    def add_helm(self, **kwargs):
        return self._internal_add_helm(calling_frame_source(), **kwargs)

    def _add_helm(self, template, source):
        errors = list(HELM_VALIDATOR.iter_errors(template))
        if errors:
            for error in errors:
                self.logger.error("Error detected in Helm template from %s", source, exc_info=error)
            raise errors[0]

        return self._internal_add_helm(source, **{k.replace("-", "_"): v for k, v in template.items()})

    def _add_repository(self, repository: str):
        repository_hash = sha256(repository.encode("UTF-8")).hexdigest()
        logger.debug("Repository %s mapping to %s", repository, repository_hash)
        if repository_hash not in self.repositories:
            logger.info("Adding and updating repository %s mapping to %s", repository, repository_hash)
            self.context.app.run(self.helm_stanza() + ["repo", "add", repository_hash, repository],
                                 stdout_logger,
                                 stderr_logger).wait()
            self.context.app.run(self.helm_stanza() + ["repo", "update"],
                                 stdout_logger,
                                 stderr_logger).wait()
            self.repositories.add(repository_hash)

        return repository_hash

    def _internal_add_helm(self, source, *, repository, chart, version, name, namespace, include_crds,
                           values=None, values_file=None):
        if values and values_file:
            raise RuntimeError(f"In {source} either values or values file may be specified, but not both")

        if values_file:
            values_file = Path(values_file)
            if not values_file.is_absolute():
                values_file = self.context.app.cwd / values_file

        repository_hash = self._add_repository(repository)
        stdin = DEVNULL

        if values:
            def write_stdin():
                return json.dumps(values)

            stdin = write_stdin

        resources = self.context.app.run_capturing_out(self.helm_stanza() +
                                                       ["template",
                                                        name,
                                                        f"{repository_hash}/{chart}",
                                                        "--version", version,
                                                        "-n", namespace,
                                                        "-a", ",".join(self.context.k8s.get_api_versions())
                                                        ] +
                                                       (["--include-crds"] if include_crds else []) +
                                                       (["-f", values_file] if values_file else []) +
                                                       (["-f", "-"] if values else []),
                                                       stderr_logger,
                                                       stdin=stdin,
                                                       )

        def helm_namespace_transformer(resources: Sequence[K8SResource],
                                       resource: K8SResource):
            if resource.rdef.namespaced and not resource.namespace:
                resource.namespace = namespace
                return resource

        if self.context.helm.namespace_transformer:
            self.context.k8s.add_transformer(helm_namespace_transformer)

        self.context.k8s.add_resources(yaml.safe_load_all(resources), source)

        if self.context.helm.namespace_transformer:
            self.context.k8s.remove_transformer(helm_namespace_transformer)

    def __repr__(self):
        return "Helm Plugin"
