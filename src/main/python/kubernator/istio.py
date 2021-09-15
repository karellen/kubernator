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
import tempfile
from pathlib import Path

import yaml
from jsonpath_ng.ext import parse as jp_parse
from kubernetes import client
from kubernetes.client.rest import ApiException

from kubernator.api import (KubernatorPlugin, scan_dir,
                            TemplateEngine,
                            load_remote_file,
                            FileType,
                            StripNL,
                            Globs)
from kubernator.k8s import K8SResourcePluginMixin

logger = logging.getLogger("kubernator.istio")
proc_logger = logger.getChild("istio")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)

MESH_PILOT_JP = jp_parse('$.meshVersion[?Component="pilot"].Info.version')

OBJECT_SCHEMA_VERSION = "1.20.6"


class IstioPlugin(KubernatorPlugin, K8SResourcePluginMixin):
    logger = logger

    def __init__(self):
        self.context = None
        self.client_version = None
        self.server_version = None
        self.provision_operator = False
        self.istio_stanza = ["istioctl"]
        self.template_engine = TemplateEngine(logger)
        super().__init__()

    def set_context(self, context):
        self.context = context

    def handle_init(self):
        context = self.context
        context.globals.istio = dict(
            default_includes=Globs(["*.istio.yaml", "*.istio.yml"], True),
            default_excludes=Globs([".*"], True),
        )

    def handle_start(self):
        context = self.context
        self.istio_stanza += ["--kubeconfig", os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))]

        version_out: str = context.app.run_capturing_out(self.istio_stanza + ["version", "-o", "json"],
                                                         stderr_logger)

        version = json.loads(version_out)["clientVersion"]["version"]
        logger.info("Found Istio client version %s", version)

        self.client_version = version.split(".")
        mesh_versions = set(m.value.split(".") for m in MESH_PILOT_JP.find(version_out))
        if mesh_versions:
            self.server_version = max(mesh_versions)

        if not self.server_version:
            logger.info("No Istio mesh has been found and it'll be created")
            self.provision_operator = True
        elif self.server_version < self.client_version:
            logger.info("Istio client is version %s while server is up to %s - operator will be upgraded",
                        ".".join(self.client_version),
                        ".".join(self.server_version))
            self.provision_operator = True

        # Register Istio-related CRDs with K8S
        url_prefix = (f"https://raw.githubusercontent.com/istio/istio/{'.'.join(self.client_version)}/"
                      "manifests/charts/base/crds")
        self.context.k8s.load_remote_crds(f"{url_prefix}/crd-all.gen.yaml", "yaml")

        # This plugin only deals with Istio Operator, so only load that stuff
        self.resource_definitions_schema = load_remote_file(logger,
                                                            f"https://raw.githubusercontent.com/kubernetes/kubernetes/"
                                                            f"v{OBJECT_SCHEMA_VERSION}/api/openapi-spec/swagger.json",
                                                            FileType.JSON)
        self._populate_resource_definitions()
        self.add_remote_crds(f"{url_prefix}/crd-operator.yaml", FileType.YAML)

        # Exclude Istio YAMLs from K8S resource loading
        context.k8s.default_excludes.add("*.istio.yaml")
        context.k8s.default_excludes.add("*.istio.yml")

    def handle_before_dir(self, cwd: Path):
        context = self.context

        context.istio.default_includes = Globs(context.istio.default_includes)
        context.istio.default_excludes = Globs(context.istio.default_excludes)
        context.istio.includes = Globs(context.istio.default_includes)
        context.istio.excludes = Globs(context.istio.default_excludes)

    def handle_after_dir(self, cwd: Path):
        context = self.context
        istio = context.istio

        for f in scan_dir(logger, cwd, lambda d: d.is_file(), istio.excludes, istio.includes):
            p = cwd / f.name
            display_p = context.app.display_path(p)
            logger.debug("Adding Istio Operator from %s", display_p)

            with open(p, "rt") as file:
                template = self.template_engine.from_string(file.read())

            self.add_resources(template.render({"ktor": context}), display_p)

    def handle_apply(self):
        context = self.context

        if not self.resources:
            logger.info("Skipping Istio as no Operator was processed")
        else:
            with tempfile.NamedTemporaryFile(mode="wt", delete=False) as operators_file:
                yaml.safe_dump_all((r.manifest for r in self.resources.values()), operators_file)

            if context.app.args.command == "apply":
                logger.info("Running Istio precheck")
                context.app.run(self.istio_stanza + ["x", "precheck", "-f", operators_file.name],
                                stdout_logger, stderr_logger).wait()

                self._operator_init(operators_file, True)

                if not context.app.args.dry_run:
                    self._operator_init(operators_file, False)

    def _operator_init(self, operators_file, dry_run):
        context = self.context

        status_details = " (dry run)" if dry_run else ""

        k8s_client = context.k8s.k8s_client
        logger.info("Creating istio-system namespace%s", status_details)
        istio_system = self.add_resource({"apiVersion": "v1",
                                          "kind": "Namespace",
                                          "metadata": {
                                              "labels": {
                                                  "istio-injection": "disabled"
                                              },
                                              "name": "istio-system"
                                          }})
        istio_system.rdef.populate_api(client, k8s_client)
        try:
            istio_system.create(dry_run=dry_run)
        except ApiException as e:
            skip = False
            if e.status == 409:
                status = json.loads(e.body)
                if status["reason"] == "AlreadyExists":
                    skip = True
            if not skip:
                raise

        logger.info("Running Istio operator init%s", status_details)
        istio_operator_init = self.istio_stanza + ["operator", "init", "-f", operators_file.name]
        context.app.run(istio_operator_init + (["--dry-run"] if dry_run else []),
                        stdout_logger,
                        stderr_logger).wait()

    def __repr__(self):
        return "Istio Plugin"
