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
import tempfile
from pathlib import Path

import yaml

from kubernator.api import (KubernatorPlugin,
                            StripNL,
                            get_golang_os,
                            get_golang_machine,
                            prepend_os_path,
                            get_cache_dir,
                            CalledProcessError,
                            )

logger = logging.getLogger("kubernator.kind")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)

KIND_CLUSTER_LABEL = "io.x-k8s.kind.cluster"

DEFAULT_NODE_IMAGE_REGISTRY = "ghcr.io/karellen/kindest-node"


class KindPlugin(KubernatorPlugin):
    logger = logger

    _name = "kind"

    def __init__(self):
        self.context = None
        self.kind_dir = None
        self.kubeconfig_dir = None
        self._config_path = None
        super().__init__()

    def set_context(self, context):
        self.context = context

    def _resolve_latest_tag(self, repo_url):
        """Return highest v<major>.<minor>.<patch> tag from a GitHub repo via git ls-remote.
        Skips pre-release tags like v0.1.0-alpha, v0.2.0-rc.1."""
        versions = self.context.app.run_capturing_out(
            ["git", "ls-remote", "-t", "--refs", repo_url, "v*"],
            stderr_logger,
        )
        tuples = []
        for line in versions.splitlines():
            if not line:
                continue
            # "<sha>\trefs/tags/v1.2.3" -> "1.2.3"
            tag = line.split()[1][11:]
            parts = tag.split(".")
            if len(parts) != 3:
                continue
            if not all(p.isdigit() for p in parts):
                continue
            tuples.append(tuple(int(p) for p in parts))
        if not tuples:
            raise RuntimeError(f"No numeric v<major>.<minor>.<patch> tags found at {repo_url}")
        return ".".join(str(x) for x in sorted(tuples)[-1])

    def get_latest_kind_version(self):
        return self._resolve_latest_tag("https://github.com/kubernetes-sigs/kind")

    def cmd(self, *extra_args):
        stanza, env = self._stanza(list(extra_args))
        return self.context.app.run(stanza, stdout_logger, stderr_logger, env=env).wait()

    def cmd_out(self, *extra_args):
        stanza, env = self._stanza(list(extra_args))
        return self.context.app.run_capturing_out(stanza, stderr_logger, env=env)

    def _stanza(self, extra_args):
        context = self.context
        kind = context.kind
        stanza = [kind.kind_file] + extra_args
        env = dict(os.environ)
        env["KUBECONFIG"] = str(kind.kubeconfig)
        if kind.provider == "podman":
            env["KIND_EXPERIMENTAL_PROVIDER"] = "podman"
        return stanza, env

    def _docker_ps(self, *filters, all_containers=True):
        args = ["docker", "ps", "-q"]
        if all_containers:
            args.append("-a")
        for f in filters:
            args += ["--filter", f]
        out = self.context.app.run_capturing_out(args, stderr_logger).strip()
        return [line for line in out.splitlines() if line]

    def _cluster_containers(self, profile, running=None, all_containers=True):
        filters = [f"label={KIND_CLUSTER_LABEL}={profile}"]
        if running is True:
            filters.append("status=running")
        elif running is False:
            filters.append("status=exited")
        return self._docker_ps(*filters, all_containers=all_containers)

    def _cluster_exists(self, profile):
        out = self.cmd_out("get", "clusters")
        return profile in {line.strip() for line in out.splitlines() if line.strip()}

    def _detect_provider(self, provider):
        context = self.context
        cmd_debug_logger = StripNL(proc_logger.debug)

        def probe(binary):
            try:
                context.app.run([binary, "info"], cmd_debug_logger, cmd_debug_logger).wait()
                return True
            except (FileNotFoundError, CalledProcessError) as e:
                logger.trace("%s is NOT functional", binary, exc_info=e)
                return False

        if provider:
            if not probe(provider):
                raise RuntimeError(f"Requested kind provider {provider!r} is not functional")
            return provider

        if probe("docker"):
            logger.info("Docker is functional, selecting 'docker' as the kind provider")
            return "docker"
        if probe("podman"):
            logger.info("Podman is functional, selecting 'podman' as the kind provider")
            return "podman"
        raise RuntimeError("No kind provider is functional. Tried 'docker' and 'podman'.")

    def register(self,
                 kind_version=None,
                 profile="default",
                 k8s_version=None,
                 node_image=None,
                 node_image_registry=DEFAULT_NODE_IMAGE_REGISTRY,
                 keep_running=False,
                 start_fresh=False,
                 nodes=1,
                 control_plane_nodes=1,
                 provider=None,
                 config=None,
                 extra_port_mappings=None,
                 feature_gates=None,
                 runtime_config=None):
        context = self.context

        context.app.register_plugin("kubeconfig")

        if not k8s_version and not node_image:
            msg = "Either k8s_version or node_image must be specified for kind"
            logger.critical(msg)
            raise RuntimeError(msg)

        if nodes < 1:
            raise RuntimeError(f"kind requires nodes >= 1, got {nodes}")
        if control_plane_nodes < 1:
            raise RuntimeError(f"kind requires control_plane_nodes >= 1, got {control_plane_nodes}")
        if control_plane_nodes > nodes:
            raise RuntimeError(
                f"control_plane_nodes ({control_plane_nodes}) cannot exceed nodes ({nodes})")

        k8s_version_tuple = tuple(map(int, k8s_version.split("."))) if k8s_version else None

        if not kind_version:
            kind_version = self.get_latest_kind_version()
            logger.info("No kind version is specified, latest is %s", kind_version)

        kind_dl_file, _ = context.app.download_remote_file(
            logger,
            f"https://github.com/kubernetes-sigs/kind/releases/download/v{kind_version}/"
            f"kind-{get_golang_os()}-{get_golang_machine()}",
            "bin",
        )
        os.chmod(kind_dl_file, 0o500)

        self.kind_dir = tempfile.TemporaryDirectory()
        context.app.register_cleanup(self.kind_dir)
        kind_file = Path(self.kind_dir.name) / "kind"
        kind_file.symlink_to(kind_dl_file)
        prepend_os_path(self.kind_dir.name)

        version_out: str = context.app.run_capturing_out(
            [str(kind_file), "version"], stderr_logger).strip()
        # "kind v0.31.0 go1.22.1 linux/amd64"
        version = version_out.split()[1].lstrip("v") if version_out else kind_version
        logger.info("Found kind %s in %s", version, kind_file)

        profile_dir = get_cache_dir("kind")
        self.kubeconfig_dir = profile_dir / ".kube" / profile
        self.kubeconfig_dir.mkdir(parents=True, exist_ok=True)
        kubeconfig_path = self.kubeconfig_dir / "config"

        resolved_provider = self._detect_provider(provider)

        if not node_image and k8s_version:
            node_image = f"{node_image_registry}:v{k8s_version}"

        context.globals.kind = dict(
            version=version,
            kind_file=str(kind_file),
            profile=profile,
            k8s_version=k8s_version,
            k8s_version_tuple=k8s_version_tuple,
            node_image=node_image,
            node_image_registry=node_image_registry,
            start_fresh=start_fresh,
            keep_running=keep_running,
            nodes=nodes,
            control_plane_nodes=control_plane_nodes,
            provider=resolved_provider,
            config=config,
            extra_port_mappings=list(extra_port_mappings) if extra_port_mappings else [],
            feature_gates=dict(feature_gates) if feature_gates else {},
            runtime_config=dict(runtime_config) if runtime_config else {},
            kubeconfig=str(kubeconfig_path),
            cmd=self.cmd,
            cmd_out=self.cmd_out,
        )
        context.kubeconfig.kubeconfig = context.kind.kubeconfig

        logger.info("Kind kubeconfig is %s", context.kind.kubeconfig)
        logger.info("Kind node image is %s", node_image)

    def _generate_cluster_config(self):
        kind = self.context.kind
        if kind.config:
            return kind.config

        needs_config = (kind.nodes > 1
                        or kind.control_plane_nodes > 1
                        or kind.extra_port_mappings
                        or kind.feature_gates
                        or kind.runtime_config)
        if not needs_config:
            return None

        doc = {
            "kind": "Cluster",
            "apiVersion": "kind.x-k8s.io/v1alpha4",
        }
        if kind.feature_gates:
            doc["featureGates"] = {k: bool(v) for k, v in kind.feature_gates.items()}
        if kind.runtime_config:
            doc["runtimeConfig"] = {k: str(v) for k, v in kind.runtime_config.items()}

        node_list = []
        for i in range(kind.control_plane_nodes):
            entry = {"role": "control-plane"}
            if i == 0 and kind.extra_port_mappings:
                entry["extraPortMappings"] = [dict(m) for m in kind.extra_port_mappings]
            node_list.append(entry)
        for _ in range(kind.nodes - kind.control_plane_nodes):
            node_list.append({"role": "worker"})
        doc["nodes"] = node_list

        return yaml.safe_dump(doc, sort_keys=False)

    def _write_cluster_config(self):
        config_yaml = self._generate_cluster_config()
        if not config_yaml:
            self._config_path = None
            return None
        self._config_path = Path(self.kind_dir.name) / "cluster.yaml"
        self._config_path.write_text(config_yaml)
        logger.debug("Wrote kind cluster config to %s:\n%s", self._config_path, config_yaml)
        return self._config_path

    def _export_kubeconfig(self):
        kind = self.context.kind
        self.cmd("export", "kubeconfig",
                 "--name", kind.profile,
                 "--kubeconfig", str(kind.kubeconfig))
        logger.info("Exported kubeconfig for cluster %r to %s", kind.profile, kind.kubeconfig)

    def _docker(self, *args, capture=False):
        cmd_args = ["docker", *args]
        if capture:
            return self.context.app.run_capturing_out(cmd_args, stderr_logger)
        return self.context.app.run(cmd_args, stdout_logger, stderr_logger).wait()

    def kind_create(self):
        kind = self.context.kind
        args = ["create", "cluster", "--name", kind.profile, "--wait", "120s"]
        if kind.node_image:
            args += ["--image", kind.node_image]
        config_path = self._write_cluster_config()
        if config_path:
            args += ["--config", str(config_path)]
        logger.info("Creating kind cluster %r (image=%s, nodes=%d, control_plane_nodes=%d)",
                    kind.profile, kind.node_image, kind.nodes, kind.control_plane_nodes)
        self.cmd(*args)

    def kind_delete(self):
        kind = self.context.kind
        logger.warning("Deleting kind cluster %r", kind.profile)
        try:
            self.cmd("delete", "cluster", "--name", kind.profile)
        except CalledProcessError as e:
            logger.warning("kind delete failed for %r: %s", kind.profile, e)

    def kind_stop(self):
        kind = self.context.kind
        running = self._cluster_containers(kind.profile, running=True)
        if not running:
            logger.info("Kind cluster %r has no running containers", kind.profile)
            return
        logger.info("Stopping %d container(s) for kind cluster %r", len(running), kind.profile)
        self._docker("stop", *running)

    def kind_start(self):
        kind = self.context.kind
        if self._cluster_exists(kind.profile):
            stopped = self._cluster_containers(kind.profile, running=False)
            running = self._cluster_containers(kind.profile, running=True)
            if stopped and not running:
                logger.info("Starting %d stopped container(s) for kind cluster %r",
                            len(stopped), kind.profile)
                self._docker("start", *stopped)
            elif stopped and running:
                logger.info("Resuming %d stopped container(s) for kind cluster %r",
                            len(stopped), kind.profile)
                self._docker("start", *stopped)
            else:
                logger.info("Kind cluster %r is already running", kind.profile)
        else:
            self.kind_create()

        self._export_kubeconfig()

        context = self.context
        context.app.register_plugin("kubectl", version=kind.k8s_version)

    def handle_start(self):
        kind = self.context.kind
        if kind.start_fresh:
            if self._cluster_exists(kind.profile):
                self.kind_delete()
        self.kind_start()

    def handle_shutdown(self):
        kind = self.context.kind
        if kind.keep_running:
            logger.warning("Keeping kind cluster %r running", kind.profile)
            return
        self.kind_stop()

    def __repr__(self):
        return "Kind Plugin"
