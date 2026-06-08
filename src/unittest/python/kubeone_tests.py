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

from gevent.monkey import patch_all, is_anything_patched

if not is_anything_patched():
    patch_all()

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from kubernator.api import PropertyDict, Globs
from kubernator.plugins.kubeone import KubeOnePlugin


def _make_context(**overrides):
    global_ctx = PropertyDict()
    global_ctx.globals = global_ctx
    ctx = PropertyDict(_parent=global_ctx)
    ctx.app = dict(
        register_plugin=MagicMock(),
        register_cleanup=MagicMock(),
        download_remote_file=MagicMock(),
        run=MagicMock(),
        run_capturing_out=MagicMock(),
        display_path=lambda p: str(p),
        args=types.SimpleNamespace(command="dump", dry_run=True),
    )
    ctx.kubeconfig = dict(set=MagicMock())
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


class KubeOnePluginRegisterTest(unittest.TestCase):
    def test_register_system_binary_not_found(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)

        with patch("kubernator.plugins.kubeone.which", return_value=None):
            with self.assertRaises(RuntimeError) as cm:
                plugin.register()
            self.assertIn("kubeone", str(cm.exception))

    def test_register_system_binary_found(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)

        version_json = json.dumps({
            "kubeone": {"gitVersion": "v1.9.1", "gitCommit": "abc123"},
            "machine_controller": {"gitVersion": "v1.60.0"}
        })

        with patch("kubernator.plugins.kubeone.which", return_value="/usr/bin/kubeone"):
            ctx.app["run_capturing_out"] = MagicMock(return_value=version_json)
            plugin.register()

        self.assertEqual(plugin.kubeone_file, "/usr/bin/kubeone")
        self.assertEqual(ctx.kubeone.version, "1.9.1")
        ctx.app["register_plugin"].assert_called_once_with("kubeconfig")

    def test_register_version_fallback_on_invalid_json(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)

        with patch("kubernator.plugins.kubeone.which", return_value="/usr/bin/kubeone"):
            ctx.app["run_capturing_out"] = MagicMock(return_value="kubeone version 1.8.0")
            plugin.register()

        self.assertEqual(ctx.kubeone.version, "kubeone version 1.8.0")

    def test_register_download_version(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)

        work_dir = tempfile.TemporaryDirectory()
        kubeone_bin = Path(work_dir.name) / "kubeone"
        kubeone_bin.touch()

        zip_dir = tempfile.TemporaryDirectory()
        zip_path = Path(zip_dir.name) / "kubeone.zip"
        import zipfile
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(kubeone_bin, "kubeone")

        ctx.app["download_remote_file"] = MagicMock(return_value=(zip_path, False))

        version_json = json.dumps({
            "kubeone": {"gitVersion": "v1.9.1"},
            "machine_controller": {"gitVersion": "v1.60.0"}
        })
        ctx.app["run_capturing_out"] = MagicMock(return_value=version_json)

        try:
            plugin.register(version="1.9.1")

            ctx.app["download_remote_file"].assert_called_once()
            call_args = ctx.app["download_remote_file"].call_args
            url = call_args[0][1]
            self.assertIn("kubeone_1.9.1_", url)
            self.assertIn(".zip", url)
            self.assertEqual(ctx.kubeone.version, "1.9.1")
        finally:
            work_dir.cleanup()
            zip_dir.cleanup()
            if plugin._work_dir:
                plugin._work_dir.cleanup()
            if plugin.kubeone_dir:
                plugin.kubeone_dir.cleanup()


class KubeOnePluginStanzaTest(unittest.TestCase):
    def test_stanza_without_manifest(self):
        plugin = KubeOnePlugin()
        plugin.kubeone_file = "/usr/bin/kubeone"
        plugin._manifest_path = None
        self.assertEqual(plugin.stanza(), ["/usr/bin/kubeone"])

    def test_stanza_with_manifest(self):
        plugin = KubeOnePlugin()
        plugin.kubeone_file = "/usr/bin/kubeone"
        plugin._manifest_path = Path("/tmp/kubeone.yaml")
        stanza = plugin.stanza()
        self.assertEqual(stanza[0], "/usr/bin/kubeone")
        self.assertIn("--manifest", stanza)
        self.assertIn("/tmp/kubeone.yaml", stanza)


class KubeOnePluginInitTest(unittest.TestCase):
    def test_handle_init_sets_defaults(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)
        plugin.handle_init()

        includes = ctx.kubeone.default_includes
        self.assertIn("*.kubeone.yaml", includes)
        self.assertIn("*.kubeone.yml", includes)

    def test_handle_before_dir_resets_globs(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)
        plugin.handle_init()

        plugin.handle_before_dir(Path("/some/dir"))
        self.assertIsNotNone(ctx.kubeone.includes)
        self.assertIsNotNone(ctx.kubeone.excludes)


class KubeOnePluginApplyTest(unittest.TestCase):
    def _make_plugin(self, command="apply", dry_run=False):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        ctx.app["args"] = types.SimpleNamespace(command=command, dry_run=dry_run)
        plugin.set_context(ctx)
        plugin.kubeone_file = "/usr/bin/kubeone"
        plugin._manifest_path = Path("/tmp/kubeone.yaml")
        plugin._work_dir = tempfile.TemporaryDirectory()
        kubeconfig_path = str(Path(plugin._work_dir.name) / "config")
        ctx.globals.kubeone = dict(kubeconfig=kubeconfig_path)
        return plugin, ctx

    def test_apply_raises_without_manifest(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)
        plugin._manifest_path = None
        with self.assertRaises(RuntimeError) as cm:
            plugin.apply()
        self.assertIn("No KubeOne manifest", str(cm.exception))

    def test_apply_dry_run_does_not_execute(self):
        plugin, ctx = self._make_plugin(command="apply", dry_run=True)
        try:
            mock_run = MagicMock()
            ctx.app["run"] = mock_run
            plugin.apply()
            mock_run.assert_not_called()
        finally:
            plugin._work_dir.cleanup()

    def test_apply_dump_mode_does_not_execute(self):
        plugin, ctx = self._make_plugin(command="dump", dry_run=False)
        try:
            mock_run = MagicMock()
            ctx.app["run"] = mock_run
            plugin.apply()
            mock_run.assert_not_called()
        finally:
            plugin._work_dir.cleanup()

    def test_apply_executes_with_auto_approve(self):
        plugin, ctx = self._make_plugin(command="apply", dry_run=False)
        try:
            mock_runner = MagicMock()
            mock_runner.wait = MagicMock()
            mock_run = MagicMock(return_value=mock_runner)
            ctx.app["run"] = mock_run
            ctx.app["run_capturing_out"] = MagicMock(return_value="apiVersion: v1\nkind: Config\n")

            plugin.apply()

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertIn("apply", cmd)
            self.assertIn("--auto-approve", cmd)
        finally:
            plugin._work_dir.cleanup()


class KubeOnePluginResetTest(unittest.TestCase):
    def test_reset_raises_without_manifest(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)
        plugin._manifest_path = None
        with self.assertRaises(RuntimeError) as cm:
            plugin.reset()
        self.assertIn("No KubeOne manifest", str(cm.exception))

    def test_reset_dry_run_does_not_execute(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        ctx.app["args"] = types.SimpleNamespace(command="apply", dry_run=True)
        plugin.set_context(ctx)
        plugin.kubeone_file = "/usr/bin/kubeone"
        plugin._manifest_path = Path("/tmp/kubeone.yaml")

        mock_run = MagicMock()
        ctx.app["run"] = mock_run
        plugin.reset()
        mock_run.assert_not_called()

    def test_reset_executes_with_auto_approve(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        ctx.app["args"] = types.SimpleNamespace(command="apply", dry_run=False)
        plugin.set_context(ctx)
        plugin.kubeone_file = "/usr/bin/kubeone"
        plugin._manifest_path = Path("/tmp/kubeone.yaml")
        plugin._work_dir = tempfile.TemporaryDirectory()

        try:
            mock_runner = MagicMock()
            mock_runner.wait = MagicMock()
            mock_run = MagicMock(return_value=mock_runner)
            ctx.app["run"] = mock_run

            plugin.reset()

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertIn("reset", cmd)
            self.assertIn("--auto-approve", cmd)
        finally:
            plugin._work_dir.cleanup()


class KubeOnePluginTfJsonTest(unittest.TestCase):
    def test_tfjson_args_without_terraform(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)
        self.assertEqual(plugin._tfjson_args(), [])

    def test_tfjson_args_with_terraform(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        ctx.tf = {}
        ctx.tf["cluster_name"] = "test-cluster"
        ctx.tf["api_endpoint"] = "10.0.0.1"
        plugin.set_context(ctx)
        plugin._work_dir = tempfile.TemporaryDirectory()

        try:
            args = plugin._tfjson_args()
            self.assertEqual(len(args), 2)
            self.assertEqual(args[0], "--tfjson")

            with open(args[1]) as f:
                tf_data = json.load(f)
            self.assertEqual(tf_data["cluster_name"]["value"], "test-cluster")
            self.assertEqual(tf_data["api_endpoint"]["value"], "10.0.0.1")
        finally:
            plugin._work_dir.cleanup()


class KubeOnePluginKubeconfigExportTest(unittest.TestCase):
    def test_kubeconfig_export_raises_without_manifest(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)
        plugin._manifest_path = None
        with self.assertRaises(RuntimeError) as cm:
            plugin.kubeconfig_export()
        self.assertIn("No KubeOne manifest", str(cm.exception))

    def test_kubeconfig_export_writes_and_registers(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)
        plugin.kubeone_file = "/usr/bin/kubeone"
        plugin._manifest_path = Path("/tmp/kubeone.yaml")
        plugin._work_dir = tempfile.TemporaryDirectory()

        kubeconfig_content = "apiVersion: v1\nkind: Config\nclusters: []\n"
        kubeconfig_path = str(Path(plugin._work_dir.name) / "config")
        ctx.globals.kubeone = dict(kubeconfig=kubeconfig_path)
        ctx.app["run_capturing_out"] = MagicMock(return_value=kubeconfig_content)

        try:
            plugin.kubeconfig_export()

            with open(kubeconfig_path) as f:
                self.assertEqual(f.read(), kubeconfig_content)
            ctx.kubeconfig["set"].assert_called_once_with(kubeconfig_path)
        finally:
            plugin._work_dir.cleanup()


class KubeOnePluginStatusTest(unittest.TestCase):
    def test_status_raises_without_manifest(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)
        plugin._manifest_path = None
        with self.assertRaises(RuntimeError) as cm:
            plugin.status()
        self.assertIn("No KubeOne manifest", str(cm.exception))

    def test_status_runs_command(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)
        plugin.kubeone_file = "/usr/bin/kubeone"
        plugin._manifest_path = Path("/tmp/kubeone.yaml")
        plugin._work_dir = tempfile.TemporaryDirectory()

        try:
            mock_runner = MagicMock()
            mock_runner.wait = MagicMock()
            mock_run = MagicMock(return_value=mock_runner)
            ctx.app["run"] = mock_run

            plugin.status()

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertIn("status", cmd)
        finally:
            plugin._work_dir.cleanup()


class KubeOnePluginHandleStartTest(unittest.TestCase):
    def test_excludes_kubeone_from_k8s_when_present(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        ctx.k8s = dict(default_excludes=Globs([".*"]))
        plugin.set_context(ctx)

        plugin.handle_start()

        excludes = ctx.k8s.default_excludes
        self.assertIn("*.kubeone.yaml", excludes)
        self.assertIn("*.kubeone.yml", excludes)

    def test_no_error_without_k8s_plugin(self):
        plugin = KubeOnePlugin()
        ctx = _make_context()
        plugin.set_context(ctx)
        plugin.handle_start()


if __name__ == "__main__":
    unittest.main()
