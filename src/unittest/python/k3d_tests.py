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

from gevent.monkey import patch_all, is_anything_patched

if not is_anything_patched():
    patch_all()

import unittest
from unittest.mock import MagicMock

import yaml

from kubernator.api import PropertyDict
from kubernator.plugins.k3d import K3dPlugin


def _make_plugin(**k3d_overrides):
    """Build a K3dPlugin wired to a context whose `k3d` namespace has
    the supplied overrides on top of single-node defaults."""
    defaults = dict(
        profile="t",
        nodes=1,
        control_plane_nodes=1,
        node_image="rancher/k3s:v1.34.6-k3s1",
        config=None,
        extra_port_mappings=[],
        feature_gates={},
        runtime_config={},
        k3s_server_args=[],
        k3s_agent_args=[],
    )
    defaults.update(k3d_overrides)

    ctx = PropertyDict()
    ctx.k3d = defaults
    plugin = K3dPlugin()
    plugin.set_context(ctx)
    return plugin


class K3dGenerateConfigTest(unittest.TestCase):
    def test_returns_none_for_default_single_node(self):
        plugin = _make_plugin()
        self.assertIsNone(plugin._generate_cluster_config())

    def test_passthrough_raw_config_overrides_generation(self):
        raw = "apiVersion: k3d.io/v1alpha5\nkind: Simple\nservers: 7\nagents: 9\n"
        plugin = _make_plugin(config=raw, nodes=5, control_plane_nodes=3,
                              extra_port_mappings=[
                                  {"hostPort": 8080, "containerPort": 80},
                                  {"hostPort": 8443, "containerPort": 443}])
        self.assertEqual(plugin._generate_cluster_config(), raw)

    def test_multi_node_emits_servers_agents_and_image(self):
        plugin = _make_plugin(nodes=5, control_plane_nodes=3)
        doc = yaml.safe_load(plugin._generate_cluster_config())
        self.assertEqual(doc["apiVersion"], "k3d.io/v1alpha5")
        self.assertEqual(doc["kind"], "Simple")
        self.assertEqual(doc["servers"], 3)
        self.assertEqual(doc["agents"], 2)
        self.assertEqual(doc["image"], "rancher/k3s:v1.34.6-k3s1")
        self.assertNotIn("ports", doc)
        self.assertNotIn("options", doc)

    def test_extra_port_mappings_render_under_loadbalancer(self):
        mappings = [
            {"hostPort": 8080, "containerPort": 80, "protocol": "TCP"},
            {"hostPort": 8443, "containerPort": 443},
        ]
        plugin = _make_plugin(extra_port_mappings=mappings)
        doc = yaml.safe_load(plugin._generate_cluster_config())
        self.assertEqual(len(doc["ports"]), 2)
        self.assertEqual(doc["ports"][0],
                         {"port": "8080:80/TCP", "nodeFilters": ["loadbalancer"]})
        self.assertEqual(doc["ports"][1],
                         {"port": "8443:443", "nodeFilters": ["loadbalancer"]})

    def test_feature_gates_and_runtime_config_become_apiserver_args(self):
        plugin = _make_plugin(
            feature_gates={"FeatureA": True, "FeatureB": False},
            runtime_config={"api/v1": "true", "batch/v2alpha1": "true"},
        )
        doc = yaml.safe_load(plugin._generate_cluster_config())
        extra = doc["options"]["k3s"]["extraArgs"]
        # Two distinct args: one feature-gates, one runtime-config; both server-only.
        gate_arg = next(e for e in extra if "feature-gates" in e["arg"])
        cfg_arg = next(e for e in extra if "runtime-config" in e["arg"])
        self.assertEqual(gate_arg["nodeFilters"], ["server:*"])
        self.assertEqual(cfg_arg["nodeFilters"], ["server:*"])
        self.assertIn("FeatureA=true", gate_arg["arg"])
        self.assertIn("FeatureB=false", gate_arg["arg"])
        self.assertIn("api/v1=true", cfg_arg["arg"])
        self.assertIn("batch/v2alpha1=true", cfg_arg["arg"])
        self.assertTrue(gate_arg["arg"].startswith("--kube-apiserver-arg=feature-gates="))
        self.assertTrue(cfg_arg["arg"].startswith("--kube-apiserver-arg=runtime-config="))

    def test_k3s_server_and_agent_args_partition_correctly(self):
        plugin = _make_plugin(
            k3s_server_args=["--disable=traefik", "--disable=servicelb"],
            k3s_agent_args=["--node-label=role=edge", "--node-taint=key=val:NoSchedule"],
        )
        doc = yaml.safe_load(plugin._generate_cluster_config())
        extra = doc["options"]["k3s"]["extraArgs"]
        servers = [e for e in extra if e["nodeFilters"] == ["server:*"]]
        agents = [e for e in extra if e["nodeFilters"] == ["agent:*"]]
        self.assertEqual([e["arg"] for e in servers],
                         ["--disable=traefik", "--disable=servicelb"])
        self.assertEqual([e["arg"] for e in agents],
                         ["--node-label=role=edge", "--node-taint=key=val:NoSchedule"])


class K3dValidationTest(unittest.TestCase):
    def _register(self, **kw):
        plugin = K3dPlugin()
        ctx = PropertyDict()
        ctx.app = dict(register_plugin=MagicMock())
        plugin.set_context(ctx)
        return plugin.register(**kw)

    def test_requires_k8s_version_or_node_image(self):
        with self.assertRaises(RuntimeError) as cm:
            self._register()
        self.assertIn("k8s_version", str(cm.exception))

    def test_rejects_zero_nodes(self):
        with self.assertRaises(RuntimeError):
            self._register(k8s_version="1.34.6", nodes=0)

    def test_rejects_zero_control_plane_nodes(self):
        with self.assertRaises(RuntimeError):
            self._register(k8s_version="1.34.6", control_plane_nodes=0)

    def test_rejects_control_plane_exceeding_total(self):
        with self.assertRaises(RuntimeError) as cm:
            self._register(k8s_version="1.34.6", nodes=2, control_plane_nodes=3)
        self.assertIn("cannot exceed", str(cm.exception))


class K3dProviderTest(unittest.TestCase):
    def test_rejects_non_docker_provider(self):
        plugin = K3dPlugin()
        ctx = PropertyDict()
        ctx.app = dict(run=MagicMock())
        plugin.set_context(ctx)
        with self.assertRaises(RuntimeError) as cm:
            plugin._detect_provider("podman")
        self.assertIn("docker", str(cm.exception))


class K3dLatestTagTest(unittest.TestCase):
    def test_picks_highest_stable_tag(self):
        plugin = K3dPlugin()
        ctx = PropertyDict()
        ls_remote_out = "\n".join([
            "abc123\trefs/tags/v5.6.0",
            "def456\trefs/tags/v5.7.4",
            "789abc\trefs/tags/v5.7.5-rc.1",  # pre-release, must be skipped
            "111222\trefs/tags/v5.7.3",
            "333444\trefs/tags/v5.10.0",
        ])
        ctx.app = dict(run_capturing_out=MagicMock(return_value=ls_remote_out))
        plugin.set_context(ctx)
        self.assertEqual(plugin._resolve_latest_tag("https://example/repo"),
                         "5.10.0")


if __name__ == "__main__":
    unittest.main()
