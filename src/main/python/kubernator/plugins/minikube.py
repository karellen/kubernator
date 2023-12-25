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

from kubernator.api import (KubernatorPlugin,
                            StripNL,
                            get_golang_os,
                            get_golang_machine,
                            prepend_os_path,
                            get_cache_dir,
                            CalledProcessError
                            )

logger = logging.getLogger("kubernator.minikube")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)


class MinikubePlugin(KubernatorPlugin):
    logger = logger

    _name = "minikube"

    def __init__(self):
        self.context = None
        self.minikube_dir = None
        self.minikube_home_dir = None
        self.kubeconfig_dir = None

        super().__init__()

    def set_context(self, context):
        self.context = context

    def get_latest_minikube_version(self):
        context = self.context
        versions = context.app.run_capturing_out(["git", "ls-remote", "-t", "--refs",
                                                  "https://github.com/kubernetes/minikube", "v*"],
                                                 stderr_logger)

        # 06e3b0cf7999f74fc52af362b42fb21076ade64a        refs/tags/v1.9.1
        # "refs/tags/v1.9.1"
        # "1.9.1"
        # ("1","9","1")
        # (1, 9, 1)
        # sort and get latest, which is the last/highest
        # "v1.9.1"
        return (".".join(map(str, sorted(list(map(lambda v: tuple(map(int, v)),
                                                  filter(lambda v: len(v) == 3,
                                                         map(lambda line: line.split()[1][11:].split("."),
                                                             versions.splitlines(False))))))[-1])))

    def cmd(self, *extra_args):
        stanza, env = self._stanza(list(extra_args))
        return self.context.app.run(stanza, stdout_logger, stderr_logger, env=env).wait()

    def cmd_out(self, *extra_args):
        stanza, env = self._stanza(list(extra_args))
        return self.context.app.run_capturing_out(stanza, stderr_logger, env=env)

    def _stanza(self, extra_args):
        context = self.context
        minikube = context.minikube
        stanza = [context.minikube.minikube_file, "-p", minikube.profile] + extra_args
        env = dict(os.environ)
        env["MINIKUBE_HOME"] = str(self.minikube_home_dir)
        env["KUBECONFIG"] = str(minikube.kubeconfig)
        return stanza, env

    def register(self, minikube_version=None, profile="default", k8s_version=None,
                 keep_running=False, start_fresh=False,
                 nodes=1, driver=None, cpus="no-limit", extra_args=None):
        context = self.context

        context.app.register_plugin("kubeconfig")

        if not k8s_version:
            msg = "No Kubernetes version is specified for Minikube"
            logger.critical(msg)
            raise RuntimeError(msg)

        if not minikube_version:
            minikube_version = self.get_latest_minikube_version()
            logger.info("No minikube version is specified, latest is %s", minikube_version)

        minikube_dl_file, _ = context.app.download_remote_file(logger,
                                                               f"https://github.com/kubernetes/minikube/releases"
                                                               f"/download/v{minikube_version}/"
                                                               f"minikube-{get_golang_os()}-{get_golang_machine()}",
                                                               "bin")

        os.chmod(minikube_dl_file, 0o500)
        self.minikube_dir = tempfile.TemporaryDirectory()
        context.app.register_cleanup(self.minikube_dir)

        minikube_file = Path(self.minikube_dir.name) / "minikube"
        minikube_file.symlink_to(minikube_dl_file)
        prepend_os_path(self.minikube_dir.name)
        version_out: str = self.context.app.run_capturing_out([str(minikube_file), "version", "--short"],
                                                              stderr_logger).strip()
        version = version_out[1:]
        logger.info("Found minikube %s in %s", version, minikube_file)

        profile_dir = get_cache_dir("minikube")
        self.minikube_home_dir = profile_dir
        self.minikube_home_dir.mkdir(parents=True, exist_ok=True)
        self.kubeconfig_dir = profile_dir / ".kube"
        self.kubeconfig_dir.mkdir(parents=True, exist_ok=True)

        if not driver:
            driver = "docker"
            if get_golang_os() == "darwin":
                logger.debug("Auto-detecting Minikube driver on MacOS...")
                cmd_debug_logger = StripNL(proc_logger.debug)
                try:
                    context.app.run(["docker", "info"], cmd_debug_logger, cmd_debug_logger).wait()
                    logger.info("Docker is functional, selecting 'docker' as the driver for Minikube")
                except (FileNotFoundError, CalledProcessError) as e:
                    logger.trace("Docker is NOT functional", exc_info=e)
                    driver = "hyperkit"
                    try:
                        context.app.run(["hyperkit", "-v"], cmd_debug_logger, cmd_debug_logger).wait()
                        logger.info("Hyperkit is functional, selecting 'hyperkit' as the driver for Minikube")
                    except (FileNotFoundError, CalledProcessError) as e:
                        logger.trace("Hyperkit is NOT functional", exc_info=e)
                        driver = "podman"
                        try:
                            context.app.run(["podman", "info"], cmd_debug_logger, cmd_debug_logger).wait()
                            logger.info("Podman is functional, selecting 'podman' as the driver for Minikube")
                        except (FileNotFoundError, CalledProcessError) as e:
                            logger.trace("Podman is NOT functional", exc_info=e)
                            raise RuntimeError("No Minikube driver is functional on MacOS. "
                                               "Tried 'docker', 'hyperkit' and 'podman'!")

        context.globals.minikube = dict(version=version,
                                        minikube_file=str(minikube_file),
                                        profile=profile,
                                        k8s_version=k8s_version,
                                        start_fresh=start_fresh,
                                        keep_running=keep_running,
                                        nodes=nodes,
                                        driver=driver,
                                        cpus=cpus,
                                        extra_args=extra_args or [],
                                        kubeconfig=str(self.kubeconfig_dir / "config"),
                                        cmd=self.cmd,
                                        cmd_out=self.cmd_out
                                        )
        context.kubeconfig.kubeconfig = context.minikube.kubeconfig

        logger.info("Minikube Home is %s", self.minikube_home_dir)
        logger.info("Minikube Kubeconfig is %s", context.minikube.kubeconfig)

    def minikube_is_running(self):
        try:
            out = self.cmd_out("status", "-o", "json")
            logger.info("Minikube profile %r is running: %s", self.context.minikube.profile,
                        out.strip())
            return True
        except CalledProcessError as e:
            logger.info("Minikube profile %r is not running: %s", self.context.minikube.profile,
                        e.output.strip())
            return False

    def minikube_start(self):
        minikube = self.context.minikube
        if not self.minikube_is_running():
            logger.info("Starting minikube profile %r...", minikube.profile)
            args = ["start",
                    "--driver", str(minikube.driver),
                    "--kubernetes-version", str(minikube.k8s_version),
                    "--wait", "apiserver",
                    "--nodes", str(minikube.nodes)]

            if minikube.driver == "docker":
                args.extend(["--cpus", str(minikube.cpus)])

            self.cmd(*args)
        else:
            logger.warning("Minikube profile %r is already running!", minikube.profile)

        logger.info("Updating minikube profile %r context", minikube.profile)
        self.cmd("update-context")

    def minikube_stop(self):
        minikube = self.context.minikube
        if self.minikube_is_running():
            logger.info("Shutting down minikube profile %r...", minikube.profile)
            self.cmd("stop", "-o", "json")

    def minikube_delete(self):
        minikube = self.context.minikube
        self.minikube_stop()
        logger.warning("Deleting minikube profile %r!", minikube.profile)
        self.cmd("delete")

    def handle_start(self):
        minikube = self.context.minikube
        if minikube.start_fresh:
            self.minikube_delete()

        self.minikube_start()

    def handle_shutdown(self):
        minikube = self.context.minikube
        if not minikube.keep_running:
            self.minikube_stop()
        else:
            logger.warning("Will keep minikube profile %s running!", minikube.profile)

    def __repr__(self):
        return "Minikube Plugin"
