# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2024 Karellen, Inc.
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
import http.client
import json
import logging
import os
import socket
import ssl
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import yaml

from kubernator.api import (KubernatorPlugin,
                            StripNL,
                            get_golang_os,
                            get_golang_machine,
                            prepend_os_path,
                            get_cache_dir,
                            CalledProcessError,
                            )

logger = logging.getLogger("kubernator.k3d")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)

K3D_CLUSTER_LABEL = "k3d.cluster"

DEFAULT_NODE_IMAGE_REGISTRY = "rancher/k3s"
DEFAULT_NODE_IMAGE_SUFFIX = "-k3s1"


class K3dPlugin(KubernatorPlugin):
    logger = logger

    _name = "k3d"

    def __init__(self):
        self.context = None
        self.k3d_dir = None
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

    def get_latest_k3d_version(self):
        return self._resolve_latest_tag("https://github.com/k3d-io/k3d")

    def cmd(self, *extra_args):
        stanza, env = self._stanza(list(extra_args))
        return self.context.app.run(stanza, stdout_logger, stderr_logger, env=env).wait()

    def cmd_out(self, *extra_args):
        stanza, env = self._stanza(list(extra_args))
        return self.context.app.run_capturing_out(stanza, stderr_logger, env=env)

    def _stanza(self, extra_args):
        context = self.context
        k3d = context.k3d
        stanza = [k3d.k3d_file] + extra_args
        env = dict(os.environ)
        env["KUBECONFIG"] = str(k3d.kubeconfig)
        return stanza, env

    def _docker_ps(self, *filters, all_containers=True):
        args = ["docker", "ps", "-q"]
        if all_containers:
            args.append("-a")
        for f in filters:
            args += ["--filter", f]
        out = self.context.app.run_capturing_out(args, stderr_logger).strip()
        return [line for line in out.splitlines() if line]

    def _cluster_containers(self, profile, all_containers=True):
        filters = [f"label={K3D_CLUSTER_LABEL}={profile}"]
        return self._docker_ps(*filters, all_containers=all_containers)

    def _cluster_exists(self, profile):
        out = self.cmd_out("cluster", "list", "-o", "json")
        try:
            clusters = json.loads(out) if out.strip() else []
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Unable to parse `k3d cluster list -o json` output: {e}") from e
        return any(c.get("name") == profile for c in clusters)

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

        if provider and provider != "docker":
            raise RuntimeError(
                f"k3d only supports the 'docker' provider; got {provider!r}")

        if probe("docker"):
            logger.info("Docker is functional, selecting 'docker' as the k3d provider")
            return "docker"
        raise RuntimeError("Docker is not functional; k3d requires Docker.")

    def register(self,
                 k3d_version=None,
                 profile="default",
                 k8s_version=None,
                 node_image=None,
                 node_image_registry=DEFAULT_NODE_IMAGE_REGISTRY,
                 node_image_suffix=DEFAULT_NODE_IMAGE_SUFFIX,
                 keep_running=False,
                 start_fresh=False,
                 nodes=1,
                 control_plane_nodes=1,
                 provider=None,
                 config=None,
                 extra_port_mappings=None,
                 feature_gates=None,
                 runtime_config=None,
                 k3s_server_args=None,
                 k3s_agent_args=None):
        context = self.context

        context.app.register_plugin("kubeconfig")

        if not k8s_version and not node_image:
            msg = "Either k8s_version or node_image must be specified for k3d"
            logger.critical(msg)
            raise RuntimeError(msg)

        if nodes < 1:
            raise RuntimeError(f"k3d requires nodes >= 1, got {nodes}")
        if control_plane_nodes < 1:
            raise RuntimeError(f"k3d requires control_plane_nodes >= 1, got {control_plane_nodes}")
        if control_plane_nodes > nodes:
            raise RuntimeError(
                f"control_plane_nodes ({control_plane_nodes}) cannot exceed nodes ({nodes})")

        k8s_version_tuple = tuple(map(int, k8s_version.split("."))) if k8s_version else None

        if not k3d_version:
            k3d_version = self.get_latest_k3d_version()
            logger.info("No k3d version is specified, latest is %s", k3d_version)

        k3d_dl_file, _ = context.app.download_remote_file(
            logger,
            f"https://github.com/k3d-io/k3d/releases/download/v{k3d_version}/"
            f"k3d-{get_golang_os()}-{get_golang_machine()}",
            "bin",
        )
        os.chmod(k3d_dl_file, 0o500)

        self.k3d_dir = tempfile.TemporaryDirectory()
        context.app.register_cleanup(self.k3d_dir)
        k3d_file = Path(self.k3d_dir.name) / "k3d"
        k3d_file.symlink_to(k3d_dl_file)
        prepend_os_path(self.k3d_dir.name)

        version_out: str = context.app.run_capturing_out(
            [str(k3d_file), "version"], stderr_logger).strip()
        # "k3d version v5.7.4\nk3s version v1.30.4-k3s1 (default)"
        version = k3d_version
        for line in version_out.splitlines():
            line = line.strip()
            if line.startswith("k3d version "):
                version = line[len("k3d version "):].lstrip("v")
                break
        logger.info("Found k3d %s in %s", version, k3d_file)

        profile_dir = get_cache_dir("k3d")
        self.kubeconfig_dir = profile_dir / ".kube" / profile
        self.kubeconfig_dir.mkdir(parents=True, exist_ok=True)
        kubeconfig_path = self.kubeconfig_dir / "config"

        resolved_provider = self._detect_provider(provider)

        if not node_image and k8s_version:
            node_image = f"{node_image_registry}:v{k8s_version}{node_image_suffix}"

        context.globals.k3d = dict(
            version=version,
            k3d_file=str(k3d_file),
            profile=profile,
            k8s_version=k8s_version,
            k8s_version_tuple=k8s_version_tuple,
            node_image=node_image,
            node_image_registry=node_image_registry,
            node_image_suffix=node_image_suffix,
            start_fresh=start_fresh,
            keep_running=keep_running,
            nodes=nodes,
            control_plane_nodes=control_plane_nodes,
            provider=resolved_provider,
            config=config,
            extra_port_mappings=list(extra_port_mappings) if extra_port_mappings else [],
            feature_gates=dict(feature_gates) if feature_gates else {},
            runtime_config=dict(runtime_config) if runtime_config else {},
            k3s_server_args=list(k3s_server_args) if k3s_server_args else [],
            k3s_agent_args=list(k3s_agent_args) if k3s_agent_args else [],
            kubeconfig=str(kubeconfig_path),
            cmd=self.cmd,
            cmd_out=self.cmd_out,
        )
        context.kubeconfig.kubeconfig = context.k3d.kubeconfig

        logger.info("k3d kubeconfig is %s", context.k3d.kubeconfig)
        logger.info("k3d node image is %s", node_image)

    def _generate_cluster_config(self):
        k3d = self.context.k3d
        if k3d.config:
            return k3d.config

        agents = k3d.nodes - k3d.control_plane_nodes
        needs_config = (k3d.control_plane_nodes > 1
                        or agents > 0
                        or k3d.extra_port_mappings
                        or k3d.feature_gates
                        or k3d.runtime_config
                        or k3d.k3s_server_args
                        or k3d.k3s_agent_args)
        if not needs_config:
            return None

        doc = {
            "apiVersion": "k3d.io/v1alpha5",
            "kind": "Simple",
            "servers": k3d.control_plane_nodes,
            "agents": agents,
        }
        if k3d.node_image:
            doc["image"] = k3d.node_image

        if k3d.extra_port_mappings:
            ports = []
            for m in k3d.extra_port_mappings:
                host_port = m["hostPort"]
                container_port = m["containerPort"]
                protocol = m.get("protocol")
                spec = f"{host_port}:{container_port}"
                if protocol:
                    spec = f"{spec}/{protocol}"
                ports.append({"port": spec, "nodeFilters": ["loadbalancer"]})
            doc["ports"] = ports

        extra_args = []
        if k3d.feature_gates:
            gates = ",".join(f"{k}={'true' if v else 'false'}"
                             for k, v in k3d.feature_gates.items())
            extra_args.append({
                "arg": f"--kube-apiserver-arg=feature-gates={gates}",
                "nodeFilters": ["server:*"],
            })
        if k3d.runtime_config:
            cfg = ",".join(f"{k}={v}" for k, v in k3d.runtime_config.items())
            extra_args.append({
                "arg": f"--kube-apiserver-arg=runtime-config={cfg}",
                "nodeFilters": ["server:*"],
            })
        for arg in k3d.k3s_server_args:
            extra_args.append({"arg": arg, "nodeFilters": ["server:*"]})
        for arg in k3d.k3s_agent_args:
            extra_args.append({"arg": arg, "nodeFilters": ["agent:*"]})
        if extra_args:
            doc["options"] = {"k3s": {"extraArgs": extra_args}}

        return yaml.safe_dump(doc, sort_keys=False)

    def _write_cluster_config(self):
        config_yaml = self._generate_cluster_config()
        if not config_yaml:
            self._config_path = None
            return None
        self._config_path = Path(self.k3d_dir.name) / "cluster.yaml"
        self._config_path.write_text(config_yaml)
        logger.debug("Wrote k3d cluster config to %s:\n%s", self._config_path, config_yaml)
        return self._config_path

    def _export_kubeconfig(self):
        k3d = self.context.k3d
        config_yaml = self.cmd_out("kubeconfig", "get", k3d.profile)
        Path(k3d.kubeconfig).write_text(config_yaml)
        logger.info("Wrote kubeconfig for cluster %r to %s", k3d.profile, k3d.kubeconfig)

    def k3d_create(self):
        k3d = self.context.k3d
        args = ["cluster", "create", k3d.profile, "--wait", "--timeout", "120s"]
        config_path = self._write_cluster_config()
        if config_path:
            args += ["--config", str(config_path)]
            # When a config file is supplied, image/servers/agents are inside it;
            # passing them again on the CLI is rejected by k3d as a conflict.
        else:
            if k3d.node_image:
                args += ["--image", k3d.node_image]
        logger.info("Creating k3d cluster %r (image=%s, nodes=%d, control_plane_nodes=%d)",
                    k3d.profile, k3d.node_image, k3d.nodes, k3d.control_plane_nodes)
        self.cmd(*args)

    def k3d_delete(self):
        k3d = self.context.k3d
        logger.warning("Deleting k3d cluster %r", k3d.profile)
        try:
            self.cmd("cluster", "delete", k3d.profile)
        except CalledProcessError as e:
            logger.warning("k3d delete failed for %r: %s", k3d.profile, e)

    def k3d_stop(self):
        k3d = self.context.k3d
        if not self._cluster_exists(k3d.profile):
            logger.info("k3d cluster %r does not exist; nothing to stop", k3d.profile)
            return
        logger.info("Stopping k3d cluster %r", k3d.profile)
        try:
            self.cmd("cluster", "stop", k3d.profile)
        except CalledProcessError as e:
            logger.warning("k3d stop failed for %r: %s", k3d.profile, e)

    def k3d_start(self):
        k3d = self.context.k3d
        resumed = False
        if self._cluster_exists(k3d.profile):
            logger.info("Starting existing k3d cluster %r", k3d.profile)
            self.cmd("cluster", "start", k3d.profile, "--wait", "--timeout", "120s")
            resumed = True
        else:
            self.k3d_create()

        self._export_kubeconfig()

        # On resume, k3d's --wait may return before the apiserver is fully
        # answering /readyz over TLS. Poll until it does so downstream
        # plugins don't see SSL handshake failures.
        if resumed:
            self._wait_for_apiserver()

        context = self.context
        context.app.register_plugin("kubectl", version=k3d.k8s_version)

    def _wait_for_apiserver(self, timeout=120):
        with open(self.context.k3d.kubeconfig) as f:
            cfg = yaml.safe_load(f)
        server_url = cfg["clusters"][0]["cluster"]["server"]
        parsed = urlparse(server_url)
        ssl_ctx = ssl._create_unverified_context()

        logger.info("Waiting up to %ds for apiserver at %s to be ready",
                    timeout, server_url)
        deadline = time.monotonic() + timeout
        last_err = None
        while time.monotonic() < deadline:
            try:
                conn = http.client.HTTPSConnection(parsed.hostname, parsed.port,
                                                   context=ssl_ctx, timeout=5)
                try:
                    conn.request("GET", "/readyz")
                    resp = conn.getresponse()
                    status = resp.status
                    resp.read()
                finally:
                    conn.close()
                if status == 200:
                    logger.info("Apiserver at %s is ready", server_url)
                    return
                last_err = f"HTTP {status}"
            except (OSError, socket.error, ssl.SSLError,
                    http.client.HTTPException) as e:
                last_err = f"{type(e).__name__}: {e}"
            time.sleep(2)
        raise RuntimeError(
            f"Apiserver at {server_url} did not become ready within {timeout}s: {last_err}")

    def handle_start(self):
        k3d = self.context.k3d
        if k3d.start_fresh:
            if self._cluster_exists(k3d.profile):
                self.k3d_delete()
        self.k3d_start()

    def handle_shutdown(self):
        k3d = self.context.k3d
        if k3d.keep_running:
            logger.warning("Keeping k3d cluster %r running", k3d.profile)
            return
        self.k3d_stop()

    def __repr__(self):
        return "k3d Plugin"
