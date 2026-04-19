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

from kubernator.api import KubernatorPlugin, PropertyDict


class StubPlugin(KubernatorPlugin):
    _name = "stub"

    def __init__(self, name):
        self._name = name
        self.context = None
        self.handler_calls = []

    def set_context(self, context):
        self.context = context

    def handle_after_dir(self, cwd):
        self.handler_calls.append(("after_dir", cwd))


class CrossPluginCallPlugin(KubernatorPlugin):
    """Plugin that calls into another plugin's method during its handler,
    simulating the template→k8s cross-plugin reentry pattern."""
    _name = "caller"

    def __init__(self, target):
        self._target = target
        self.context = None
        self.target_context_was_set = None

    def set_context(self, context):
        self.context = context

    def handle_after_dir(self, cwd):
        self.target_context_was_set = self._target.context is not None


class DispatchToAllPluginsTests(unittest.TestCase):
    def test_all_plugins_have_context_during_handler(self):
        """All plugins must have their context set while any handler in the
        same phase is executing — not just the one currently being called."""
        ctx = PropertyDict()
        target = StubPlugin("target")
        caller = CrossPluginCallPlugin(target)
        ctx._plugins = [target, caller]

        from kubernator.app import App
        app = App.__new__(App)
        app.context = ctx

        def run(h):
            h_f = getattr(h, "handle_after_dir", None)
            if h_f:
                h_f(Path("/dummy"))

        app._dispatch_to_all_plugins(True, ctx, run)

        self.assertTrue(caller.target_context_was_set,
                        "target plugin's context was None during caller's handler "
                        "(cross-plugin reentry broken)")

    def test_contexts_cleared_after_phase(self):
        ctx = PropertyDict()
        p1 = StubPlugin("p1")
        p2 = StubPlugin("p2")
        ctx._plugins = [p1, p2]

        from kubernator.app import App
        app = App.__new__(App)
        app.context = ctx

        app._dispatch_to_all_plugins(False, ctx, lambda h: None)

        self.assertIsNone(p1.context)
        self.assertIsNone(p2.context)

    def test_contexts_cleared_even_on_exception(self):
        ctx = PropertyDict()
        p1 = StubPlugin("p1")
        p2 = StubPlugin("p2")
        ctx._plugins = [p1, p2]

        from kubernator.app import App
        app = App.__new__(App)
        app.context = ctx

        def exploding_run(h):
            if h._name == "p2":
                raise ValueError("boom")

        with self.assertRaises(ValueError):
            app._dispatch_to_all_plugins(False, ctx, exploding_run)

        self.assertIsNone(p1.context)
        self.assertIsNone(p2.context)

    def test_reverse_order_respected(self):
        ctx = PropertyDict()
        call_order = []
        p1 = StubPlugin("p1")
        p2 = StubPlugin("p2")
        ctx._plugins = [p1, p2]

        from kubernator.app import App
        app = App.__new__(App)
        app.context = ctx

        def tracking_run(h):
            call_order.append(h._name)

        app._dispatch_to_all_plugins(True, ctx, tracking_run)
        self.assertEqual(call_order, ["p2", "p1"])

        call_order.clear()
        app._dispatch_to_all_plugins(False, ctx, tracking_run)
        self.assertEqual(call_order, ["p1", "p2"])


if __name__ == "__main__":
    unittest.main()
