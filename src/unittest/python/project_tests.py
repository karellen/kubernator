# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2026 Karellen, Inc.
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
from pathlib import Path
from types import SimpleNamespace

from kubernator.api import PropertyDict
from kubernator.app import App
from kubernator.plugins.project import ProjectPlugin


def _make_app_and_contexts(k8s_present=False, k8s_resources=None):
    """Build an App, run its handle_init to install the project descriptor on
    globals.app.project, and return (app, globals, dir_ctx). The caller sets
    ``app.context`` to the dir context it wants to operate on before invoking
    plugin.register or ``ctx.app.project = ...``.
    """
    args = SimpleNamespace(path=Path("."))
    app = App(args)
    app.handle_init()
    g = app._top_level_context._PropertyDict__parent  # global context
    if k8s_present:
        k8s_plugin = SimpleNamespace(resources=dict(k8s_resources or {}))
        g.k8s = dict(_k8s=k8s_plugin)
    dir_ctx = app._top_dir_context
    app.context = dir_ctx
    return app, g, dir_ctx


class ProjectPluginRegistrationTests(unittest.TestCase):
    def test_register_without_k8s_sets_project_and_switch(self):
        app, g, ctx = _make_app_and_contexts(k8s_present=False)
        plugin = ProjectPlugin()
        plugin.set_context(ctx)

        plugin.register(name="alpha")

        self.assertEqual(ctx.app.project, "alpha")
        self.assertIn("project", g)
        self.assertEqual(g.project.root, "alpha")
        self.assertEqual(g.project.cleanup, False)
        self.assertEqual(g.project.state_namespace, "kubernator-system")

    def test_register_carries_cleanup_and_state_namespace(self):
        app, g, ctx = _make_app_and_contexts(k8s_present=False)
        plugin = ProjectPlugin()
        plugin.set_context(ctx)

        plugin.register(name="alpha", cleanup=True, state_namespace="ops")

        self.assertEqual(g.project.cleanup, True)
        self.assertEqual(g.project.state_namespace, "ops")

    def test_register_with_k8s_empty_resources_allowed(self):
        app, g, ctx = _make_app_and_contexts(k8s_present=True, k8s_resources={})
        plugin = ProjectPlugin()
        plugin.set_context(ctx)

        plugin.register(name="alpha")

        self.assertEqual(ctx.app.project, "alpha")

    def test_register_fails_when_k8s_has_resources(self):
        sentinel_a = object()
        sentinel_b = object()
        app, g, ctx = _make_app_and_contexts(
            k8s_present=True,
            k8s_resources={"cm/a": sentinel_a, "cm/b": sentinel_b})
        plugin = ProjectPlugin()
        plugin.set_context(ctx)

        with self.assertRaises(RuntimeError) as exc:
            plugin.register(name="alpha")
        self.assertIn("k8s.resources is non-empty", str(exc.exception))

    def test_register_invalid_name_rejected(self):
        app, _, ctx = _make_app_and_contexts()
        plugin = ProjectPlugin()
        plugin.set_context(ctx)

        with self.assertRaises(ValueError):
            plugin.register(name="bad.name")
        with self.assertRaises(ValueError):
            plugin.register(name="has space")
        with self.assertRaises(ValueError):
            plugin.register(name="")

    def test_register_second_time_at_same_context_rejects(self):
        app, _, ctx = _make_app_and_contexts()
        plugin = ProjectPlugin()
        plugin.set_context(ctx)

        plugin.register(name="alpha")
        # Second register() on the same context tries to re-set the project
        # segment, which the App-owned descriptor rejects.
        with self.assertRaises(ValueError):
            plugin.register(name="beta")

    def test_register_in_subcontext_extends_project_name(self):
        app, _, ctx = _make_app_and_contexts()
        plugin_root = ProjectPlugin()
        plugin_root.set_context(ctx)
        plugin_root.register(name="alpha")

        sub = PropertyDict(_parent=ctx)
        # Simulate the App advancing to the sub directory.
        app.context = sub
        plugin_sub = ProjectPlugin()
        plugin_sub.set_context(sub)
        plugin_sub.register(name="beta")

        self.assertEqual(sub.app.project, "alpha.beta")

        app.context = ctx
        self.assertEqual(ctx.app.project, "alpha")

    def test_sibling_subcontexts_isolated(self):
        app, _, ctx = _make_app_and_contexts()
        plugin_root = ProjectPlugin()
        plugin_root.set_context(ctx)
        plugin_root.register(name="root")

        sub_a = PropertyDict(_parent=ctx)
        sub_b = PropertyDict(_parent=ctx)
        app.context = sub_a
        sub_a.app.project = "a"
        app.context = sub_b
        sub_b.app.project = "b"

        app.context = sub_a
        self.assertEqual(sub_a.app.project, "root.a")
        app.context = sub_b
        self.assertEqual(sub_b.app.project, "root.b")


if __name__ == "__main__":
    unittest.main()
