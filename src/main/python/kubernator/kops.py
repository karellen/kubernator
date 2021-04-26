# -*- coding: utf-8 -*-
#
# Copyright 2021 © Payperless
#

import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from kubernator.api import (KubernatorPlugin, scan_dir,
                            FileType,
                            load_file,
                            load_remote_file,
                            StringIO,
                            TemplateEngine,
                            StripNL)
from kubernator.k8s_api import K8SResourcePluginMixin

logger = logging.getLogger("kubernator.kops")

KOPS_CRDS = ["kops.k8s.io_clusters.yaml",
             "kops.k8s.io_instancegroups.yaml",
             "kops.k8s.io_keysets.yaml",
             "kops.k8s.io_sshcredentials.yaml"]

KOPS_SCHEMA_VERSION = "1.20.6"


class KopsPlugin(KubernatorPlugin, K8SResourcePluginMixin):
    logger = logger
    proc_logger = logger.getChild("kops")

    def __init__(self):
        self.context = None
        self.kops_stanza = ["kops"]
        self.version = None
        self.kops_dir = None
        self.kops_path = None
        self.kubeconfig_path: Path = None
        self.template_engine = TemplateEngine(logger)
        super().__init__()

    def set_context(self, context):
        self.context = context

    def handle_init(self):
        context = self.context

        # Temp dir
        self.kops_dir = TemporaryDirectory()
        context.app.register_cleanup(self.kops_dir)
        self.kops_path = kops_path = Path(self.kops_dir.name)
        kops_config = kops_path / ".kops.yaml"
        kops_config.touch()
        self.kops_stanza.extend(("--config", str(kops_config)))

        # Kube config dir
        kubeconfig_dir = kops_path / ".kube"
        kubeconfig_dir.mkdir()
        self.kubeconfig_path = kubeconfig_dir / "config"

        # if logger.getEffectiveLevel() < logging.DEBUG:
        #    self.kops_stanza.append("-v5")
        # elif logger.getEffectiveLevel() < logging.INFO:
        #    self.kops_stanza.append("-v2")

        context.globals.kops = dict(walk_remote=self.walk_remote,
                                    walk_local=self.walk_local,
                                    update=self.update,
                                    master_interval="8m",
                                    node_interval="8m"
                                    )
        context.kops = dict()

        self.version = context.app.run_capturing_out(["kops", "version", "--short"], logger.error).strip()
        logger.info("Found kOps version %s", self.version)

        self.resource_definitions_schema = load_remote_file(logger,
                                                            f"https://raw.githubusercontent.com/kubernetes/kubernetes/"
                                                            f"v{KOPS_SCHEMA_VERSION}/api/openapi-spec/swagger.json",
                                                            FileType.JSON, "kops")
        self._populate_resource_definitions()

        common_url_path = f"https://raw.githubusercontent.com/kubernetes/kops/v{self.version}/k8s/crds"
        for kops_crd in KOPS_CRDS:
            url = f"{common_url_path}/{kops_crd}"
            for manifest in load_remote_file(logger, url, FileType.YAML, sub_category="kops"):
                self.add_crd(manifest, url)

    def handle_start(self):
        context = self.context

        # Exclude Kops YAMLs from K8S resource loading
        context.k8s.default_excludes.add("*.kops.yaml")
        context.k8s.default_excludes.add("*.kops.yml")

    def walk_remote(self, url, *paths: Path,
                    excludes=(".*",), includes=("*.kops.yaml", "*.kops.yml")):
        repository = self.context.app.repository(url)
        for path in paths:
            self.walk_local(repository.local_dir / path, excludes, includes)

    def walk_local(self, path: Path, excludes=(".*",), includes=("*.kops.yaml", "*.kops.yml")):
        context = self.context

        for f in scan_dir(logger, path, lambda d: d.is_file(), excludes, includes):
            p = path / f.name
            display_p = context.app.display_path(p)
            logger.debug("Adding Kops resources from %s", display_p)
            template_source = load_file(logger, p, FileType.YAML, display_p)

            template = self.template_engine.from_string(template_source)

            self.add_resources(template.render({"ktor": context}), display_p)

    def update(self):
        context = self.context
        run = context.app.run
        run_capturing_out = context.app.run_capturing_out
        stdout_logger = StripNL(self.proc_logger.info)
        stderr_logger = StripNL(self.proc_logger.warning)

        os.environ["KUBECONFIG"] = str(self.kubeconfig_path)
        os.environ["KOPS_CLUSTER_NAME"] = context.kops.cluster_name
        os.environ["KOPS_STATE_STORE"] = context.kops.state_store

        kops_extra_args = ["--name", context.kops.cluster_name, "--state", context.kops.state_store]

        logger.info("Exporting kubeconfig from kOps")
        run(self.kops_stanza + ["export", "kubecfg", "--admin"] + kops_extra_args,
            stdout_logger,
            stderr_logger).wait()

        if not self.kubeconfig_path.exists():
            raise RuntimeError("kOps failed to export kubeconfig for unknown reason - check AWS credentials")

        for resource in self.resources:
            logger.info("Replacing/creating kOps resource %s", resource)
            run(self.kops_stanza + ["replace", "--force", "-f", "-"] + kops_extra_args,
                stdout_logger,
                stderr_logger,
                StringIO(resource.manifest))

        logger.info("Staging kOps update")
        update_cmd = self.kops_stanza + ["update", "cluster"] + kops_extra_args
        result = run_capturing_out(update_cmd, stderr_logger)
        self.proc_logger.info(result)
        if "Must specify --yes to apply changes" in result:
            logger.info("kOps update would make changes")
            if context.app.args.dry_run:
                logger.info("Skipping actual kOps update due to dry-run")
            else:
                logger.info("Running kOps update")
                run(update_cmd + ["--yes"],
                    stdout_logger,
                    stderr_logger).wait()

        logger.info("Staging kOps cluster rolling update")
        rolling_update_cmd = self.kops_stanza + ["rolling-update", "cluster",
                                                 "--master-interval", context.kops.master_interval,
                                                 "--node-interval", context.kops.node_interval] + kops_extra_args
        result = run_capturing_out(rolling_update_cmd, stderr_logger)
        self.proc_logger.info(result)
        if "Must specify --yes to apply changes" in result:
            logger.info("kOps cluster rolling update would make changes")
            if context.app.args.dry_run:
                logger.info("Skipping actual kOps cluster rolling update due to dry-run")
            else:
                logger.info("Running kOps cluster rolling update")
                run(rolling_update_cmd + ["--yes"],
                    stdout_logger,
                    stderr_logger).wait()

    def __repr__(self):
        return "kOps Plugin"
