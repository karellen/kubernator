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

from kubernator.api import ContextProperty, PropertyDict, config_parent


def _make_segment_descriptor():
    """Composes dot-joined string segments across the parent chain. Stored at
    the top-of-chain ``descriptor_host`` PropertyDict under the name ``seg``;
    plain string segments live at descendants under the same name."""

    def get_segments(origin):
        segs = []
        cur = origin
        while cur is not None:
            v = cur._PropertyDict__dict.get("seg")
            if isinstance(v, str):
                segs.insert(0, v)
            cur = config_parent(cur)
        return ".".join(segs) if segs else None

    def set_segment(origin, value):
        if not isinstance(value, str) or "." in value:
            raise ValueError("invalid segment %r" % (value,))
        local = origin._PropertyDict__dict
        existing = local.get("seg")
        if isinstance(existing, ContextProperty):
            raise RuntimeError("refusing to overwrite descriptor at its own layer")
        if isinstance(existing, str):
            raise ValueError("already set to %r in this context" % (existing,))
        local["seg"] = value

    return ContextProperty(get_segments, set_segment)


def _install_host():
    """Return (host, child): host holds the descriptor, child is the first
    writable layer beneath it."""
    host = PropertyDict()
    host.seg = _make_segment_descriptor()
    child = PropertyDict(_parent=host)
    return host, child


class ContextPropertyTestcase(unittest.TestCase):
    def test_install_stores_descriptor_as_value(self):
        host, _ = _install_host()
        self.assertIsInstance(host._PropertyDict__dict["seg"], ContextProperty)

    def test_read_with_no_segments_yields_none(self):
        host, child = _install_host()
        self.assertIsNone(host.seg)
        self.assertIsNone(child.seg)

    def test_write_dispatches_to_descriptor_setter(self):
        host, child = _install_host()
        grandchild = PropertyDict(_parent=child)

        child.seg = "x"
        grandchild.seg = "y"

        self.assertEqual(child._PropertyDict__dict["seg"], "x")
        self.assertEqual(grandchild._PropertyDict__dict["seg"], "y")
        # Descriptor at host is untouched by segment writes.
        self.assertIsInstance(host._PropertyDict__dict["seg"], ContextProperty)

    def test_read_composes_segments_across_chain(self):
        host, child = _install_host()
        grandchild = PropertyDict(_parent=child)
        greatgrandchild = PropertyDict(_parent=grandchild)

        child.seg = "x"
        grandchild.seg = "y"
        greatgrandchild.seg = "z"

        self.assertEqual(child.seg, "x")
        self.assertEqual(grandchild.seg, "x.y")
        self.assertEqual(greatgrandchild.seg, "x.y.z")

    def test_sibling_contexts_are_isolated(self):
        host, child = _install_host()
        child.seg = "x"
        sibling_a = PropertyDict(_parent=child)
        sibling_b = PropertyDict(_parent=child)
        sibling_a.seg = "a"
        sibling_b.seg = "b"

        self.assertEqual(sibling_a.seg, "x.a")
        self.assertEqual(sibling_b.seg, "x.b")

    def test_single_local_assignment_raises_at_same_layer(self):
        _, child = _install_host()
        child.seg = "x"
        with self.assertRaises(ValueError):
            child.seg = "y"

    def test_inherited_value_does_not_count_as_local_for_duplicate(self):
        _, child = _install_host()
        child.seg = "x"
        grandchild = PropertyDict(_parent=child)

        # Reading yields the inherited composition, but grandchild has no
        # local segment yet, so the first local assignment is allowed.
        self.assertEqual(grandchild.seg, "x")
        grandchild.seg = "y"
        self.assertEqual(grandchild.seg, "x.y")

        with self.assertRaises(ValueError):
            grandchild.seg = "z"

    def test_descriptor_invalid_value_rejected(self):
        _, child = _install_host()
        with self.assertRaises(ValueError):
            child.seg = "has.dot"
        with self.assertRaises(ValueError):
            child.seg = 42

    def test_read_only_descriptor_rejects_writes(self):
        host = PropertyDict()
        host.ro = ContextProperty(lambda origin: "fixed")
        child = PropertyDict(_parent=host)

        self.assertEqual(host.ro, "fixed")
        self.assertEqual(child.ro, "fixed")
        with self.assertRaises(AttributeError):
            child.ro = "something"

    def test_descriptor_takes_priority_over_raw_local_value(self):
        _, child = _install_host()
        child.seg = "x"
        grandchild = PropertyDict(_parent=child)
        # Manually stash a non-string local value at grandchild, then verify
        # the descriptor still drives reads (ignoring the non-string).
        grandchild._PropertyDict__dict["seg"] = 99

        self.assertEqual(grandchild.seg, "x")

    def test_non_descriptor_attribute_retains_legacy_semantics(self):
        root = PropertyDict()
        root.value = 1
        child = PropertyDict(_parent=root)
        self.assertEqual(child.value, 1)

        child._PropertyDict__dict["value"] = 2
        self.assertEqual(child.value, 2)
        self.assertEqual(root.value, 1)

    def test_set_without_descriptor_falls_through_to_local_storage(self):
        root = PropertyDict()
        child = PropertyDict(_parent=root)
        child.value = 5
        self.assertEqual(child._PropertyDict__dict["value"], 5)
        self.assertNotIn("value", root._PropertyDict__dict)

    def test_dict_values_still_wrapped_when_no_descriptor(self):
        root = PropertyDict()
        root.app = {"k": "v"}
        self.assertIsInstance(root._PropertyDict__dict["app"], PropertyDict)
        self.assertEqual(root.app.k, "v")

    def test_descriptor_dispatch_through_intermediate_property_dict(self):
        # Descriptor lives on a sibling attribute chain: mirrors the plan's
        # ``globals.app.project`` layout where access is ``context.app.project``.
        globals_ctx = PropertyDict()
        globals_ctx.globals = globals_ctx
        globals_ctx.app = {"base": 1}
        # Install descriptor in the wrapped globals.app PropertyDict.
        globals_ctx.app.seg = _make_segment_descriptor()

        context = PropertyDict(_parent=globals_ctx)
        context.app = {}  # child .app chained to globals.app
        self.assertIsNone(context.app.seg)
        context.app.seg = "x"
        self.assertEqual(context.app.seg, "x")

        subdir = PropertyDict(_parent=context)
        subdir.app = {}  # per-subdir .app chained to context.app
        subdir.app.seg = "y"
        self.assertEqual(subdir.app.seg, "x.y")
        # Sibling subdir sees only its own segment plus the parent's.
        sibling = PropertyDict(_parent=context)
        sibling.app = {}
        sibling.app.seg = "z"
        self.assertEqual(sibling.app.seg, "x.z")


if __name__ == "__main__":
    unittest.main()
