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
from types import SimpleNamespace

from kubernator.plugins.k8s import (KubernetesPlugin,
                                    _encode_state, _decode_state,
                                    _project_matches,
                                    _resource_ident, _ident_key,
                                    _state_secret_name, _lease_name,
                                    PROJECT_STATE_VERSION)
from kubernator.plugins.k8s_api import K8SResourceKey


def _fake_resource(group, version, kind, name, namespace, project):
    return SimpleNamespace(
        key=K8SResourceKey(group, kind, name, namespace),
        rdef=SimpleNamespace(version=version),
        group=group, version=version, kind=kind, name=name, namespace=namespace,
        project=project,
    )


def _ident(kind, name, namespace="default", group="", version="v1"):
    return {"group": group, "version": version, "kind": kind,
            "name": name, "namespace": namespace}


class PayloadCodecTests(unittest.TestCase):
    def test_encode_decode_roundtrip(self):
        payload = {
            "version": "1",
            "finalized": True,
            "resources": {
                "alpha": [
                    {"group": "", "version": "v1", "kind": "ConfigMap",
                     "namespace": "default", "name": "cm-a"},
                    {"group": "apps", "version": "v1", "kind": "Deployment",
                     "namespace": "default", "name": "dep-a"},
                ],
                "alpha.beta": [
                    {"group": "", "version": "v1", "kind": "Service",
                     "namespace": "prod", "name": "svc-b"},
                    {"group": "", "version": "v1", "kind": "Service",
                     "namespace": "prod", "name": "svc-c"},
                ],
            },
            "pending": {},
        }
        encoded = _encode_state(payload)
        self.assertIsInstance(encoded, str)
        self.assertGreater(len(encoded), 0)
        decoded = _decode_state(encoded)
        self.assertEqual(decoded, payload)

    def test_encode_stable_across_calls(self):
        payload = {
            "version": PROJECT_STATE_VERSION,
            "finalized": False,
            "resources": {"a": [], "b": []},
            "pending": {"c": []},
        }
        a = _encode_state(payload)
        b = _encode_state(payload)
        self.assertEqual(a, b)

    def test_encode_compresses_repetitive_content(self):
        # 200 near-identical idents with the same keys; gzip should compress well.
        entries = [{"group": "apps", "version": "v1", "kind": "Deployment",
                    "namespace": "default", "name": "dep-%03d" % i}
                   for i in range(200)]
        payload = {"version": "1", "finalized": True,
                   "resources": {"alpha": entries}, "pending": {}}
        encoded = _encode_state(payload)
        # Should fit well under Kubernetes 1 MiB Secret cap with large margin.
        self.assertLess(len(encoded), 10 * 1024)


class ProjectMatcherTests(unittest.TestCase):
    def test_exact_and_prefix_match(self):
        self.assertTrue(_project_matches("alpha", "alpha"))
        self.assertTrue(_project_matches("alpha.beta", "alpha"))
        self.assertTrue(_project_matches("alpha.beta.gamma", "alpha.beta"))

    def test_does_not_match_when_not_prefix(self):
        self.assertFalse(_project_matches("alpha", "alphabet"))
        self.assertFalse(_project_matches("alphabet", "alpha"))
        self.assertFalse(_project_matches("beta", "alpha"))


class ResourceIdentTests(unittest.TestCase):
    def test_namespaced_ident(self):
        r = _fake_resource("apps", "v1", "Deployment", "d1", "ns1", "alpha")
        ident = _resource_ident(r)
        self.assertEqual(ident, {"group": "apps", "version": "v1",
                                 "kind": "Deployment", "name": "d1",
                                 "namespace": "ns1"})

    def test_cluster_scoped_ident_omits_namespace(self):
        r = _fake_resource("", "v1", "Namespace", "alpha-ns", None, "alpha")
        ident = _resource_ident(r)
        self.assertNotIn("namespace", ident)
        self.assertEqual(ident["kind"], "Namespace")

    def test_ident_key_is_hashable_and_matches_across_instances(self):
        r1 = _fake_resource("apps", "v1", "Deployment", "d1", "ns1", "alpha")
        r2 = _fake_resource("apps", "v1", "Deployment", "d1", "ns1", "alpha.beta")
        self.assertEqual(_ident_key(_resource_ident(r1)),
                         _ident_key(_resource_ident(r2)))


class NamingTests(unittest.TestCase):
    def test_names_are_deterministic(self):
        self.assertEqual(_state_secret_name("alpha"), _state_secret_name("alpha"))
        self.assertEqual(_lease_name("alpha"), _lease_name("alpha"))

    def test_names_differ_between_roots(self):
        self.assertNotEqual(_state_secret_name("alpha"), _state_secret_name("beta"))
        self.assertNotEqual(_lease_name("alpha"), _lease_name("beta"))

    def test_name_length_within_k8s_limits(self):
        # sha1 truncated to 12 chars → plenty of headroom under 253-char DNS limit.
        self.assertLessEqual(len(_state_secret_name("alpha")), 253)
        self.assertLessEqual(len(_lease_name("alpha")), 253)


def _make_plugin(project_switch=True, include=(), exclude=(),
                 cleanup=False, in_scope=None):
    """Construct a real ``KubernetesPlugin`` with a fake context so pure-logic
    methods can be exercised without touching a cluster."""
    plugin = KubernetesPlugin.__new__(KubernetesPlugin)
    plugin._resource_filters = []
    plugin._manifest_patchers = []
    plugin._in_scope_projects = set(in_scope) if in_scope is not None else None
    plugin._project_prior_state = None
    plugin._project_new_intent = None
    plugin.resources = {}

    args = SimpleNamespace(include_project=list(include),
                           exclude_project=list(exclude),
                           dry_run=False,
                           command="apply")
    app_ctx = SimpleNamespace(args=args, project=None)
    globals_entries = {}
    if project_switch:
        globals_entries["project"] = SimpleNamespace(
            root="alpha", cleanup=cleanup, state_namespace="kubernator-system")

    class _GlobalsShim:
        def __contains__(self, k):
            return k in globals_entries

        def __getattr__(self, k):
            try:
                return globals_entries[k]
            except KeyError as e:
                raise AttributeError(k) from e

    plugin.context = SimpleNamespace(globals=_GlobalsShim(), app=app_ctx, k8s=None)
    return plugin


class ScopeComputationTests(unittest.TestCase):
    def _known(self, plugin, projects):
        plugin.resources = {
            ("k", i): _fake_resource("", "v1", "ConfigMap", "cm-%d" % i, "default", p)
            for i, p in enumerate(projects)
        }

    def test_no_flags_scope_is_none(self):
        plugin = _make_plugin(project_switch=True)
        self._known(plugin, ["alpha", "alpha.beta", "alpha.gamma"])
        plugin._compute_project_scope()
        self.assertIsNone(plugin._in_scope_projects)

    def test_switch_off_scope_is_none(self):
        plugin = _make_plugin(project_switch=False, include=["alpha"])
        plugin._compute_project_scope()
        self.assertIsNone(plugin._in_scope_projects)

    def test_include_prefix_match(self):
        plugin = _make_plugin(include=["alpha.beta"])
        self._known(plugin, ["alpha", "alpha.beta", "alpha.beta.x", "alpha.gamma"])
        plugin._compute_project_scope()
        self.assertEqual(plugin._in_scope_projects,
                         {"alpha.beta", "alpha.beta.x"})

    def test_exclude_subtracts_from_includes(self):
        plugin = _make_plugin(include=["alpha"], exclude=["alpha.beta"])
        self._known(plugin, ["alpha", "alpha.beta", "alpha.beta.x", "alpha.gamma"])
        plugin._compute_project_scope()
        self.assertEqual(plugin._in_scope_projects,
                         {"alpha", "alpha.gamma"})

    def test_exclude_without_includes_uses_all_known(self):
        plugin = _make_plugin(exclude=["alpha.beta"])
        self._known(plugin, ["alpha", "alpha.beta", "alpha.gamma"])
        plugin._compute_project_scope()
        self.assertEqual(plugin._in_scope_projects,
                         {"alpha", "alpha.gamma"})

    def test_unmatched_include_pattern_fatal(self):
        plugin = _make_plugin(include=["beta"])
        self._known(plugin, ["alpha", "alpha.beta"])
        with self.assertRaises(RuntimeError) as exc:
            plugin._compute_project_scope()
        self.assertIn("-I", str(exc.exception))

    def test_unmatched_exclude_pattern_fatal(self):
        plugin = _make_plugin(exclude=["delta"])
        self._known(plugin, ["alpha", "alpha.beta"])
        with self.assertRaises(RuntimeError) as exc:
            plugin._compute_project_scope()
        self.assertIn("-X", str(exc.exception))


class ResourceFilterTests(unittest.TestCase):
    def test_filter_passes_all_when_scope_none(self):
        plugin = _make_plugin()
        plugin._in_scope_projects = None
        a = _fake_resource("", "v1", "ConfigMap", "a", "default", "alpha")
        b = _fake_resource("", "v1", "ConfigMap", "b", "default", "alpha.beta")
        self.assertTrue(plugin._project_resource_filter(a))
        self.assertTrue(plugin._project_resource_filter(b))

    def test_filter_scopes_to_in_scope_set(self):
        plugin = _make_plugin(in_scope={"alpha.beta", "alpha.beta.x"})
        matches = _fake_resource("", "v1", "ConfigMap", "b", "default", "alpha.beta")
        not_match = _fake_resource("", "v1", "ConfigMap", "a", "default", "alpha.gamma")
        self.assertTrue(plugin._project_resource_filter(matches))
        self.assertFalse(plugin._project_resource_filter(not_match))


class NewIntentComputationTests(unittest.TestCase):
    def test_groups_in_scope_resources_by_project(self):
        plugin = _make_plugin(in_scope={"alpha", "alpha.beta"})
        a1 = _fake_resource("", "v1", "ConfigMap", "a1", "default", "alpha")
        a2 = _fake_resource("", "v1", "ConfigMap", "a2", "default", "alpha")
        b1 = _fake_resource("", "v1", "ConfigMap", "b1", "prod", "alpha.beta")
        g1 = _fake_resource("", "v1", "ConfigMap", "g1", "prod", "alpha.gamma")
        plugin.resources = {("k", i): r for i, r in enumerate([a1, a2, b1, g1])}

        intent = plugin._project_compute_new_intent()
        # alpha.gamma is out of scope → not recorded.
        self.assertEqual(set(intent.keys()), {"alpha", "alpha.beta"})
        self.assertEqual(len(intent["alpha"]), 2)
        self.assertEqual(len(intent["alpha.beta"]), 1)

    def test_skips_resources_without_project(self):
        plugin = _make_plugin(in_scope=None)
        r_proj = _fake_resource("", "v1", "ConfigMap", "p1", "default", "alpha")
        r_no_proj = _fake_resource("", "v1", "ConfigMap", "x", "default", None)
        plugin.resources = {("k", 0): r_proj, ("k", 1): r_no_proj}

        intent = plugin._project_compute_new_intent()
        self.assertEqual(set(intent.keys()), {"alpha"})


class ObsoleteComputationTests(unittest.TestCase):
    def test_empty_prior_yields_no_deletions(self):
        plugin = _make_plugin(in_scope=None)
        plugin._project_prior_state = {"resources": {}, "pending": {},
                                       "finalized": True}
        plugin._project_new_intent = {
            "alpha": [_ident("ConfigMap", "a1"),
                      _ident("ConfigMap", "a2")]}
        self.assertEqual(plugin._project_compute_obsolete(), [])

    def test_removed_resource_in_prior_marked_obsolete(self):
        plugin = _make_plugin(in_scope=None)
        plugin._project_prior_state = {
            "resources": {
                "alpha": [_ident("ConfigMap", "a1"),
                          _ident("ConfigMap", "a2")]
            },
            "pending": {},
            "finalized": True,
        }
        plugin._project_new_intent = {"alpha": [_ident("ConfigMap", "a1")]}
        obsolete = plugin._project_compute_obsolete()
        self.assertEqual(len(obsolete), 1)
        self.assertEqual(obsolete[0]["name"], "a2")

    def test_resource_moved_between_projects_not_deleted(self):
        plugin = _make_plugin(in_scope=None)
        # Prior: x under alpha. Current: x under alpha.beta. Same key.
        plugin._project_prior_state = {
            "resources": {
                "alpha": [_ident("ConfigMap", "x")],
                "alpha.beta": [_ident("ConfigMap", "y")],
            },
            "pending": {},
            "finalized": True,
        }
        plugin._project_new_intent = {
            "alpha": [],
            "alpha.beta": [_ident("ConfigMap", "x"),
                           _ident("ConfigMap", "y")],
        }
        self.assertEqual(plugin._project_compute_obsolete(), [])

    def test_crashed_prior_uses_conservative_union(self):
        plugin = _make_plugin(in_scope=None)
        plugin._project_prior_state = {
            "resources": {"alpha": [_ident("ConfigMap", "a1")]},
            "pending": {
                "alpha": [_ident("ConfigMap", "a2"),
                          _ident("ConfigMap", "a3")]
            },
            "finalized": False,
        }
        plugin._project_new_intent = {"alpha": [_ident("ConfigMap", "a1")]}
        obsolete = plugin._project_compute_obsolete()
        self.assertEqual(sorted(i["name"] for i in obsolete), ["a2", "a3"])

    def test_out_of_scope_prior_projects_preserved(self):
        plugin = _make_plugin(in_scope={"alpha.beta"})
        plugin._project_prior_state = {
            "resources": {
                "alpha.beta": [_ident("ConfigMap", "b1"),
                               _ident("ConfigMap", "b2")],
                "alpha.gamma": [_ident("ConfigMap", "g1")],
            },
            "pending": {},
            "finalized": True,
        }
        plugin._project_new_intent = {
            "alpha.beta": [_ident("ConfigMap", "b1")]
        }
        obsolete = plugin._project_compute_obsolete()
        # g1 is out of scope (alpha.gamma) — not considered; only b2 is obsolete.
        self.assertEqual(sorted(i["name"] for i in obsolete), ["b2"])


class ResourceMergeTests(unittest.TestCase):
    def test_merge_overlays_in_scope_and_preserves_out_of_scope(self):
        plugin = _make_plugin(in_scope={"alpha.beta"})
        prior = {
            "alpha.beta": [_ident("ConfigMap", "old1")],
            "alpha.gamma": [_ident("ConfigMap", "g1")],
        }
        new_intent = {
            "alpha.beta": [_ident("ConfigMap", "new1"),
                           _ident("ConfigMap", "new2")]
        }
        merged = plugin._project_merge_resources(prior, new_intent)
        self.assertEqual(set(merged.keys()), {"alpha.beta", "alpha.gamma"})
        self.assertEqual(sorted(i["name"] for i in merged["alpha.beta"]),
                         ["new1", "new2"])
        self.assertEqual(merged["alpha.gamma"], [_ident("ConfigMap", "g1")])

    def test_merge_with_no_scope_filter_overlays_everything(self):
        plugin = _make_plugin(in_scope=None)
        prior = {
            "alpha": [_ident("ConfigMap", "a1")],
            "alpha.beta": [_ident("ConfigMap", "b1")],
        }
        new_intent = {"alpha": [_ident("ConfigMap", "a2")]}
        merged = plugin._project_merge_resources(prior, new_intent)
        # alpha replaced; alpha.beta absent from new_intent → dropped (it
        # would be in scope and was overlaid with nothing).
        self.assertEqual(merged, {"alpha": [_ident("ConfigMap", "a2")]})


def _true_pred(r):
    return True


def _false_pred(r):
    return False


def _identity(m):
    return m


def _none(m):
    return None


class AnnotationPatcherTests(unittest.TestCase):
    def test_stamps_annotation_when_project_active(self):
        plugin = _make_plugin(project_switch=True)
        plugin.context.app.project = "alpha.beta"
        manifest = {"apiVersion": "v1", "kind": "ConfigMap",
                    "metadata": {"name": "cm1"}}
        result = plugin._project_annotation_patcher(manifest, "test resource")
        self.assertEqual(
            result["metadata"]["annotations"]["kubernator.io/project"],
            "alpha.beta")

    def test_noop_when_project_switch_off(self):
        plugin = _make_plugin(project_switch=False)
        manifest = {"apiVersion": "v1", "kind": "ConfigMap",
                    "metadata": {"name": "cm1"}}
        result = plugin._project_annotation_patcher(manifest, "test resource")
        self.assertNotIn("annotations", result.get("metadata", {}))

    def test_raises_when_project_active_but_no_segment(self):
        plugin = _make_plugin(project_switch=True)
        plugin.context.app.project = None
        manifest = {"apiVersion": "v1", "kind": "ConfigMap"}
        with self.assertRaises(RuntimeError) as exc:
            plugin._project_annotation_patcher(manifest, "test resource desc")
        self.assertIn("no project set", str(exc.exception))

    def test_creates_metadata_and_annotations_if_absent(self):
        plugin = _make_plugin(project_switch=True)
        plugin.context.app.project = "alpha"
        manifest = {"apiVersion": "v1", "kind": "ConfigMap"}
        result = plugin._project_annotation_patcher(manifest, "test resource")
        self.assertEqual(
            result["metadata"]["annotations"]["kubernator.io/project"],
            "alpha")


class ResourceFilterAPITests(unittest.TestCase):
    def test_add_remove_resource_filter(self):
        plugin = _make_plugin()
        plugin.api_add_resource_filter(_true_pred)
        plugin.api_add_resource_filter(_false_pred)
        self.assertIn(_true_pred, plugin._resource_filters)
        self.assertIn(_false_pred, plugin._resource_filters)
        plugin.api_remove_resource_filter(_true_pred)
        self.assertNotIn(_true_pred, plugin._resource_filters)
        self.assertIn(_false_pred, plugin._resource_filters)

    def test_add_resource_filter_idempotent(self):
        plugin = _make_plugin()
        plugin.api_add_resource_filter(_true_pred)
        plugin.api_add_resource_filter(_true_pred)
        self.assertEqual(plugin._resource_filters.count(_true_pred), 1)

    def test_remove_nonexistent_resource_filter_is_noop(self):
        plugin = _make_plugin()
        plugin.api_remove_resource_filter(_true_pred)
        self.assertEqual(len(plugin._resource_filters), 0)


class TransformerValidatorAPITests(unittest.TestCase):
    def test_add_remove_transformer(self):
        plugin = _make_plugin()
        plugin._transformers = []
        plugin.api_add_transformer(_identity)
        plugin.api_add_transformer(_none)
        self.assertIn(_identity, plugin._transformers)
        self.assertIn(_none, plugin._transformers)
        plugin.api_remove_transformer(_identity)
        self.assertNotIn(_identity, plugin._transformers)
        self.assertIn(_none, plugin._transformers)

    def test_remove_nonexistent_transformer_is_noop(self):
        plugin = _make_plugin()
        plugin._transformers = []
        plugin.api_remove_transformer(_identity)

    def test_add_remove_validator(self):
        plugin = _make_plugin()
        plugin._validators = []
        plugin.api_add_validator(_identity)
        plugin.api_add_validator(_none)
        self.assertIn(_identity, plugin._validators)
        self.assertIn(_none, plugin._validators)
        plugin.api_remove_validator(_identity)
        self.assertNotIn(_identity, plugin._validators)
        self.assertIn(_none, plugin._validators)

    def test_remove_nonexistent_validator_is_noop(self):
        plugin = _make_plugin()
        plugin._validators = []
        plugin.api_remove_validator(_none)


class CleanupDisabledTests(unittest.TestCase):
    def test_obsolete_resources_skipped_when_cleanup_disabled(self):
        plugin = _make_plugin(project_switch=True, cleanup=False, in_scope=None)
        plugin._project_prior_state = {
            "resources": {
                "alpha": [_ident("ConfigMap", "old1"),
                          _ident("ConfigMap", "old2")]
            },
            "pending": {},
            "finalized": True,
        }
        plugin._project_new_intent = {"alpha": [_ident("ConfigMap", "old1")]}
        # Should return without error — no k8s API calls, just logging.
        plugin._project_delete_obsolete()
        # Verify the obsolete list was correctly computed (old2 missing from intent).
        obsolete = plugin._project_compute_obsolete()
        self.assertEqual(len(obsolete), 1)
        self.assertEqual(obsolete[0]["name"], "old2")


class PrettyApiExcDecoratorTests(unittest.TestCase):
    def test_passes_through_normal_return(self):
        from kubernator.plugins.k8s import _pretty_api_exc

        @_pretty_api_exc
        def ok():
            return 42
        self.assertEqual(ok(), 42)

    def test_normalizes_and_reraises_api_exception(self):
        from kubernator.plugins.k8s import _pretty_api_exc
        from kubernetes.client.rest import ApiException

        @_pretty_api_exc
        def boom():
            raise ApiException(status=409, reason="Conflict")

        with self.assertRaises(ApiException) as ctx:
            boom()
        self.assertEqual(ctx.exception.status, 409)

    def test_does_not_catch_non_api_exceptions(self):
        from kubernator.plugins.k8s import _pretty_api_exc

        @_pretty_api_exc
        def boom():
            raise ValueError("not an API exception")

        with self.assertRaises(ValueError):
            boom()


class LeaseLifecycleTests(unittest.TestCase):
    def test_check_renewal_noop_when_not_aborted(self):
        plugin = _make_plugin()
        plugin._project_lease_abort = False
        plugin._project_check_renewal()

    def test_check_renewal_raises_when_aborted(self):
        plugin = _make_plugin()
        plugin._project_lease_abort = True
        with self.assertRaises(RuntimeError) as ctx:
            plugin._project_check_renewal()
        self.assertIn("Lease was lost", str(ctx.exception))

    def test_start_renewal_noop_when_lease_not_acquired(self):
        plugin = _make_plugin()
        plugin._project_lease_acquired = False
        plugin._project_lease_renewer = None
        plugin._project_start_renewal()
        self.assertIsNone(plugin._project_lease_renewer)

    def test_stop_renewal_noop_when_no_renewer(self):
        plugin = _make_plugin()
        plugin._project_lease_renewer = None
        plugin._project_stop_renewal()
        self.assertIsNone(plugin._project_lease_renewer)


class HandleCleanupTests(unittest.TestCase):
    def test_noop_when_project_switch_off(self):
        plugin = _make_plugin(project_switch=False)
        plugin._project_prior_state = None
        plugin.handle_cleanup()

    def test_noop_when_prior_state_is_none(self):
        plugin = _make_plugin(project_switch=True)
        plugin._project_prior_state = None
        plugin.handle_cleanup()


class HandleShutdownTests(unittest.TestCase):
    def test_shutdown_noop_when_nothing_acquired(self):
        plugin = _make_plugin()
        plugin._project_lease_acquired = False
        plugin._project_lease_renewer = None
        plugin.handle_shutdown()
        self.assertFalse(plugin._project_lease_acquired)


if __name__ == "__main__":
    unittest.main()
