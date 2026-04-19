# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2021 Karellen, Inc.
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


import base64
import gzip
import hashlib
import json
import logging
import os
import re
import socket
import sys
import types
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from functools import partial, wraps
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Iterable, Callable, Sequence, Optional

import gevent
import jsonpatch
import yaml

from kubernator.api import (KubernatorPlugin,
                            Globs,
                            scan_dir,
                            load_file,
                            FileType,
                            StripNL,
                            install_python_k8s_client,
                            TemplateEngine,
                            calling_frame_source,
                            parse_yaml_docs)
from kubernator.merge import extract_merge_instructions, apply_merge_instructions
from kubernator.plugins import k8s_schema
from kubernator.plugins.k8s_api import (K8SResourcePluginMixin,
                                        K8SResource,
                                        K8SResourceKey,
                                        K8SResourcePatchType,
                                        K8SPropagationPolicy,
                                        PROJECT_ANNOTATION,
                                        api_exc_format_body,
                                        api_exc_normalize_body)

logger = logging.getLogger("kubernator.k8s")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)

FIELD_VALIDATION_STRICT_MARKER = "strict decoding error: "
VALID_FIELD_VALIDATION = ("Ignore", "Warn", "Strict")

PROJECT_STATE_VERSION = "1"
PROJECT_STATE_SECRET_TYPE = "kubernator.io/project-state"
PROJECT_STATE_SECRET_DATA_KEY = "state"
PROJECT_ROOT_ANNOTATION = "kubernator.io/project-root"
PROJECT_LEASE_DURATION_SECONDS = 60
PROJECT_LEASE_RENEW_INTERVAL_SECONDS = 20
PROJECT_LEASE_ACQUIRE_ATTEMPTS = 3

# State Secret payload fields — also kept as constants so the wire format
# is changed through a single declaration.
_STATE_VERSION = "version"
_STATE_FINALIZED = "finalized"
_STATE_RESOURCES = "resources"
_STATE_PENDING = "pending"


def _project_matches(p: str, q: str) -> bool:
    """Prefix match: ``p`` matches ``q`` iff ``p == q`` or ``p`` starts with
    ``q + "."``. Sub-projects of ``q`` are considered matches."""
    return p == q or p.startswith(q + ".")


def _root_hash(root: str) -> str:
    return hashlib.sha1(root.encode("utf-8")).hexdigest()[:12]


def _state_secret_name(root: str) -> str:
    return "kubernator-project-%s" % (_root_hash(root),)


def _lease_name(root: str) -> str:
    return "kubernator-project-%s-lock" % (_root_hash(root),)


def _resource_ident(resource: K8SResource) -> dict:
    """Minimal identifier dict for a K8SResource — enough to delete it on a
    subsequent run. ``version`` is needed to build ``apiVersion`` for the
    delete call; it is intentionally excluded from ``_ident_key`` so that a
    CRD version bump doesn't spuriously mark a resource obsolete."""
    key = resource.key
    ident = {
        "group": key.group or "",
        "version": resource.rdef.version,
        "kind": key.kind,
        "name": key.name,
    }
    if key.namespace:
        ident["namespace"] = key.namespace
    return ident


def _ident_key(ident: dict) -> K8SResourceKey:
    return K8SResourceKey(ident.get("group", ""),
                          ident.get("kind", ""),
                          ident.get("name", ""),
                          ident.get("namespace"))


def _encode_state(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=6)
    return base64.b64encode(compressed).decode("ascii")


def _decode_state(encoded: str) -> dict:
    compressed = base64.b64decode(encoded.encode("ascii"))
    raw = gzip.decompress(compressed)
    return json.loads(raw.decode("utf-8"))


def _empty_state_payload() -> dict:
    return {
        _STATE_VERSION: PROJECT_STATE_VERSION,
        _STATE_FINALIZED: True,
        _STATE_RESOURCES: {},
        _STATE_PENDING: {},
    }


def _lease_identity() -> str:
    """Return a unique identifier for this run — hostname-pid-uuid4."""
    return "%s-%d-%s" % (socket.gethostname(), os.getpid(), uuid.uuid4().hex[:8])


def _pretty_api_exc(func):
    """Decorator: normalize then pretty-format any ``ApiException`` that
    propagates out, so logs and error traces see indented JSON instead of
    raw bytes or ``dict`` reprs. Matches the ``_normalize_api_exc`` /
    ``api_exc_format_body`` pattern used elsewhere in k8s_api.py."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        from kubernetes.client.rest import ApiException
        try:
            return func(*args, **kwargs)
        except ApiException as e:
            api_exc_normalize_body(e)
            api_exc_format_body(e)
            raise

    return wrapper


def final_resource_validator(resources: Sequence[K8SResource],
                             resource: K8SResource,
                             error: Callable[..., Exception]) -> Iterable[Exception]:
    final_key = resource.get_manifest_key(resource.manifest)
    if final_key != resource.key:
        yield error("Illegal change of identifiers of the resource "
                    "%s from %s have been changed to %s",
                    resource.key, resource.source, final_key)

    if resource.rdef.namespaced and not resource.namespace:
        yield error("Namespaced resource %s from %s is missing the required namespace",
                    resource, resource.source)


def normalize_pkg_version(v: str):
    v_split = v.split(".")
    rev = v_split[-1]
    if not rev.isdigit():
        new_rev = ""
        for c in rev:
            if not c.isdigit():
                break
            new_rev += c
        v_split[-1] = new_rev
    return tuple(map(int, v_split))


class KubernetesPlugin(KubernatorPlugin, K8SResourcePluginMixin):
    logger = logger

    _name = "k8s"

    def __init__(self):
        super().__init__()
        self.context = None

        self.embedded_pkg_version = self._get_kubernetes_client_version()

        self._transformers = []
        self._validators = []
        self._manifest_patchers = []
        self._resource_filters = []
        self._summary = 0, 0, 0
        self._template_engine = TemplateEngine(logger)
        self._in_scope_projects: Optional[set] = None
        # Project-run state, populated when the project plugin switch is on.
        self._project_lease_identity: Optional[str] = None
        self._project_lease_acquired = False
        self._project_lease_renewer: Optional[gevent.Greenlet] = None
        self._project_lease_abort = False
        self._project_prior_state: Optional[dict] = None
        self._project_new_intent: Optional[dict] = None
        # Cached resourceVersion for the state Secret, populated by the first
        # read and refreshed after each write so subsequent writes skip their
        # own GETs.
        self._project_state_rv: Optional[str] = None

    def set_context(self, context):
        self.context = context

    def register(self,
                 field_validation="Warn",
                 field_validation_warn_fatal=True,
                 disable_client_patches=False,
                 openapi_version="auto",
                 openapi_source="auto"):
        self.context.app.register_plugin("kubeconfig")

        if field_validation not in VALID_FIELD_VALIDATION:
            raise ValueError("'field_validation' must be one of %s" % (", ".join(VALID_FIELD_VALIDATION)))

        if openapi_version not in ("auto", "v2", "v3"):
            raise ValueError("'openapi_version' must be auto|v2|v3")
        if openapi_source not in ("auto", "cluster", "github"):
            raise ValueError("'openapi_source' must be auto|cluster|github")

        context = self.context
        context.globals.k8s = dict(patch_field_excludes=("^/metadata/managedFields",
                                                         "^/metadata/generation",
                                                         "^/metadata/creationTimestamp",
                                                         "^/metadata/resourceVersion",
                                                         ),
                                   openapi_version=openapi_version,
                                   openapi_source=openapi_source,
                                   immutable_changes={("apps", "DaemonSet"): K8SPropagationPolicy.BACKGROUND,
                                                      ("apps", "StatefulSet"): K8SPropagationPolicy.ORPHAN,
                                                      ("apps", "Deployment"): K8SPropagationPolicy.ORPHAN,
                                                      ("storage.k8s.io", "StorageClass"): K8SPropagationPolicy.ORPHAN,
                                                      (None, "Pod"): K8SPropagationPolicy.BACKGROUND,
                                                      ("batch", "Job"): K8SPropagationPolicy.ORPHAN,
                                                      },
                                   default_includes=Globs(["*.yaml", "*.yml"], True),
                                   default_excludes=Globs([".*"], True),
                                   add_resources=self.add_resources,
                                   load_resources=self.api_load_resources,
                                   load_remote_resources=self.api_load_remote_resources,
                                   load_crds=self.api_load_crds,
                                   import_cluster_crds=self.api_import_cluster_crds,
                                   load_remote_crds=self.api_load_remote_crds,
                                   add_transformer=self.api_add_transformer,
                                   remove_transformer=self.api_remove_transformer,
                                   add_validator=self.api_add_validator,
                                   remove_validator=self.api_remove_validator,
                                   add_manifest_patcher=self.api_add_manifest_patcher,
                                   add_resource_filter=self.api_add_resource_filter,
                                   remove_resource_filter=self.api_remove_resource_filter,
                                   get_api_versions=self.get_api_versions,
                                   create_resource=self.create_resource,
                                   disable_client_patches=disable_client_patches,
                                   field_validation=field_validation,
                                   field_validation_warn_fatal=field_validation_warn_fatal,
                                   field_validation_warnings=0,
                                   resource_generator=self.resource_generator,
                                   resource=self.resource,
                                   conflict_retry_delay=0.3,
                                   _k8s=self,
                                   )
        context.k8s = dict(default_includes=Globs(context.globals.k8s.default_includes),
                           default_excludes=Globs(context.globals.k8s.default_excludes)
                           )
        self.api_add_validator(final_resource_validator)
        # Project hooks are always installed; they gate at runtime on
        # ``"project" in self.context.globals``.
        self.api_add_manifest_patcher(self._project_annotation_patcher)
        self.api_add_resource_filter(self._project_resource_filter)

    def handle_init(self):
        pass

    def handle_start(self):
        self.context.kubeconfig.register_change_notifier(self._kubeconfig_changed)
        self.setup_client()

    def _kubeconfig_changed(self):
        self.setup_client()

    def _get_kubernetes_client_version(self):
        return pkg_version("kubernetes").split(".")

    def setup_client(self):
        k8s = self.context.k8s
        if "server_version" not in k8s:
            self._setup_client()

        server_minor = k8s.server_version[1]

        logger.info("Using Kubernetes client version =~%s.0 for server version %s",
                    server_minor, ".".join(k8s.server_version))
        pkg_dir = install_python_k8s_client(self.context.app.run_passthrough_capturing, server_minor, logger,
                                            stdout_logger, stderr_logger, k8s.disable_client_patches)

        modules_to_delete = []
        for k, v in sys.modules.items():
            if k == "kubernetes" or k.startswith("kubernetes."):
                modules_to_delete.append(k)
        for k in modules_to_delete:
            del sys.modules[k]

        logger.info("Adding sys.path reference to %s", pkg_dir)
        sys.path.insert(0, str(pkg_dir))
        self.embedded_pkg_version = self._get_kubernetes_client_version()
        logger.info("Switching to Kubernetes client version %s", ".".join(self.embedded_pkg_version))
        self._setup_client()

        self.validator = k8s_schema.make_validator(self.context)

    def _setup_client(self):
        from kubernetes import client
        from kubernetes.client.rest import RESTResponse

        # Upstream v35 client's exceptions.py reads ``http_resp.headers`` but
        # RESTResponse only defines ``getheaders()``, so any failed API call
        # that takes the default (``_preload_content=True``) wrapping path
        # raises ``AttributeError`` inside ``ApiException.__init__`` instead
        # of surfacing the actual error. Alias the attribute once.
        if not hasattr(RESTResponse, "headers"):
            RESTResponse.headers = property(lambda self: self.getheaders())

        context = self.context
        k8s = context.k8s

        k8s.client = self._setup_k8s_client()
        version = client.VersionApi(k8s.client).get_code()
        # Strip vendor-specific suffixes so OpenAPI lookups hit upstream tags.
        # EKS/GKE use a dash (e.g. v1.28.3-eks-..., v1.28.3-gke.100);
        # k3s uses a plus sign (e.g. v1.35.3+k3s1).
        git_version = version.git_version.split("-")[0].split("+")[0]

        k8s.server_version = git_version[1:].split(".")
        k8s.server_git_version = git_version

        logger.info("Found Kubernetes %s on %s", k8s.server_git_version, k8s.client.configuration.host)

        K8SResource._k8s_client_version = normalize_pkg_version(pkg_version("kubernetes"))
        K8SResource._k8s_field_validation = k8s.field_validation
        K8SResource._k8s_field_validation_patched = not k8s.disable_client_patches
        K8SResource._logger = self.logger
        K8SResource._api_warnings = self._api_warnings

    def _api_warnings(self, resource, warn):
        k8s = self.context.k8s
        self.context.globals.k8s.field_validation_warnings += 1

        log = self.logger.warning
        if k8s.field_validation_warn_fatal:
            log = self.logger.error

        log("FAILED FIELD VALIDATION on resource %s from %s: %s", resource, resource.source, warn)

    def handle_before_dir(self, cwd: Path):
        context = self.context
        context.k8s.default_includes = Globs(context.k8s.default_includes)
        context.k8s.default_excludes = Globs(context.k8s.default_excludes)
        context.k8s.includes = Globs(context.k8s.default_includes)
        context.k8s.excludes = Globs(context.k8s.default_excludes)

    def handle_after_dir(self, cwd: Path):
        context = self.context
        k8s = context.k8s

        for f in scan_dir(logger, cwd, lambda d: d.is_file(), k8s.excludes, k8s.includes):
            p = cwd / f.name
            display_p = context.app.display_path(p)
            logger.debug("Adding Kubernetes manifest from %s", display_p)

            manifests = load_file(logger, p, FileType.YAML, display_p,
                                  self._template_engine,
                                  {"ktor": context}
                                  )

            for manifest in manifests:
                if manifest:
                    self.add_resource(manifest, display_p)

    def resource_generator(self):
        for r in self.resources.values():
            if all(f(r) for f in self._resource_filters):
                yield r

    def resource(self, manifest, source=None):
        from kubernetes import client
        if not source:
            source = calling_frame_source()
        if isinstance(manifest, str):
            docs = [m for m in parse_yaml_docs(manifest, source) if m]
            if len(docs) != 1:
                raise ValueError(f"ktor.k8s.resource() expects a single manifest document, got {len(docs)} from {source}")
            manifest = docs[0]
        res = self._create_resource(manifest, source)
        res.rdef.populate_api(client, self.context.k8s.client)
        return res

    def handle_apply(self):
        context = self.context
        k8s = context.k8s

        self._validate_resources()
        self._compute_project_scope()

        if "project" in context.globals:
            if self._project_ensure_state_namespace():
                self._project_acquire_lease()
                self._project_start_renewal()
                self._project_read_prior_state()
                self._project_write_pre_apply()
                self._project_check_renewal()

        cmd = context.app.args.command
        file_name = context.app.args.file
        file_format = context.app.args.output_format
        dry_run = context.app.args.dry_run
        dump = cmd == "dump"

        status_msg = f"{' (dump only)' if dump else ' (dry run)' if dry_run else ''}"
        if dump:
            logger.info("Will dump the changes into a file %s in %s format", file_name or "<stdout>", file_format)

        patch_field_excludes = [re.compile(e) for e in context.globals.k8s.patch_field_excludes]
        dump_results = []
        total_created, total_patched, total_deleted = 0, 0, 0
        for resource in k8s.resource_generator():
            if dump:
                resource_id = {"apiVersion": resource.api_version,
                               "kind": resource.kind,
                               "name": resource.name
                               }

                def patch_func(patch):
                    if resource.rdef.namespaced:
                        resource_id["namespace"] = resource.namespace
                    method_descriptor = {"method": "patch",
                                         "resource": resource_id,
                                         "body": patch
                                         }
                    dump_results.append(method_descriptor)
                    return resource.manifest

                def create_func():
                    method_descriptor = {"method": "create",
                                         "body": resource.manifest}
                    dump_results.append(method_descriptor)
                    return resource.manifest

                def delete_func(*, propagation_policy):
                    method_descriptor = {"method": "delete",
                                         "resource": resource_id,
                                         "propagation_policy": propagation_policy.policy
                                         }
                    dump_results.append(method_descriptor)
                    return None
            else:
                patch_func = partial(resource.patch, patch_type=K8SResourcePatchType.JSON_PATCH, dry_run=dry_run)
                create_func = partial(resource.create, dry_run=dry_run)
                delete_func = partial(resource.delete, dry_run=dry_run)

            created, patched, deleted, result = self._apply_resource(dry_run,
                                                                     patch_field_excludes,
                                                                     resource,
                                                                     patch_func,
                                                                     create_func,
                                                                     delete_func,
                                                                     status_msg)

            total_created += created
            total_patched += patched
            total_deleted += deleted

        if ((dump or dry_run) and
                k8s.field_validation_warn_fatal and self.context.globals.k8s.field_validation_warnings):
            msg = ("There were %d field validation warnings and the warnings are fatal!" %
                   self.context.globals.k8s.field_validation_warnings)
            logger.fatal(msg)
            raise RuntimeError(msg)

        if dump:
            file = open(file_name, "w") if file_name else sys.stdout
            try:
                if file_format in ("json", "json-pretty"):
                    json.dump(dump_results, file, sort_keys=True,
                              indent=4 if file_format == "json-pretty" else None)
                else:
                    yaml.safe_dump(dump_results, file)
            finally:
                if file_name:
                    file.close()
        else:
            self._summary = total_created, total_patched, total_deleted

    def handle_cleanup(self):
        if "project" not in self.context.globals:
            return
        if self._project_prior_state is None:
            # handle_apply short-circuited (dry-run against missing namespace).
            return
        self._project_check_renewal()
        # A raise from _project_delete_obsolete keeps finalized=false so the
        # next run's conservative union re-considers the not-yet-deleted keys.
        self._project_delete_obsolete()
        self._project_write_finalize()

    def handle_shutdown(self):
        try:
            self._project_stop_renewal()
        finally:
            self._project_release_lease()

    def handle_summary(self):
        total_created, total_patched, total_deleted = self._summary
        logger.info("Created %d, patched %d, deleted %d resources", total_created, total_patched, total_deleted)

    def api_load_resources(self, path: Path, file_type: str):
        return self.add_local_resources(path, FileType[file_type.upper()])

    def api_load_remote_resources(self, url: str, file_type: str, file_category=None):
        return self.add_remote_resources(url, FileType[file_type.upper()], sub_category=file_category)

    def api_load_crds(self, path: Path, file_type: str):
        return self.add_local_crds(path, FileType[file_type.upper()])

    def api_load_remote_crds(self, url: str, file_type: str, file_category=None):
        return self.add_remote_crds(url, FileType[file_type.upper()], sub_category=file_category)

    def api_import_cluster_crds(self):
        context = self.context
        k8s = context.k8s
        client = k8s.client
        from kubernetes import client as client_module

        api = client_module.ApiextensionsV1Api(client)
        crds = api.list_custom_resource_definition(watch=False)
        for crd in crds.items:
            manifest = client.sanitize_for_serialization(crd)
            manifest["apiVersion"] = "apiextensions.k8s.io/v1"
            manifest["kind"] = "CustomResourceDefinition"
            self.add_crd(manifest)

    def api_add_transformer(self, transformer):
        if transformer not in self._transformers:
            self._transformers.append(transformer)

    def api_add_validator(self, validator):
        if validator not in self._validators:
            self._validators.append(validator)

    def api_add_manifest_patcher(self, patcher):
        if patcher not in self._manifest_patchers:
            self._manifest_patchers.append(patcher)

    def api_add_resource_filter(self, pred):
        if pred not in self._resource_filters:
            self._resource_filters.append(pred)

    def api_remove_resource_filter(self, pred):
        if pred in self._resource_filters:
            self._resource_filters.remove(pred)

    def _project_annotation_patcher(self, manifest, resource_description):
        """Stamp every manifest with its ``kubernator.io/project`` annotation.
        No-op when the project plugin has not been registered."""
        if "project" not in self.context.globals:
            return manifest
        project = self.context.app.project
        if project is None:
            raise RuntimeError(
                "%s: project plugin active but no project set in this context" %
                (resource_description,))
        metadata = manifest.setdefault("metadata", {})
        annotations = metadata.setdefault("annotations", {})
        annotations[PROJECT_ANNOTATION] = project
        return manifest

    def _project_resource_filter(self, resource):
        """Scope resources by the cached ``in_scope`` set derived from
        ``-I``/``-X``. No-op when the project plugin is not active or when
        neither flag was supplied."""
        if self._in_scope_projects is None:
            return True
        return resource.project in self._in_scope_projects

    def _known_projects(self):
        """Projects present on currently-loaded manifests. Commit 8 extends
        this with prior projects recovered from the state Secret."""
        return {r.project for r in self.resources.values() if r.project}

    def _compute_project_scope(self):
        """Populate ``self._in_scope_projects`` — called once per apply run.

        * switch off → ``None`` (filter is a no-op).
        * no ``-I`` / ``-X`` given → ``None`` (every sub-project is in scope
          implicitly; annotation patcher still stamps, but no filtering).
        * otherwise, compute the in-scope set against ``known_projects``,
          validating that every pattern matches at least one known project.
        """
        self._in_scope_projects = None
        if "project" not in self.context.globals:
            return
        args = self.context.app.args
        includes = list(args.include_project or [])
        excludes = list(args.exclude_project or [])
        if not includes and not excludes:
            return

        known = self._known_projects()

        def _unmatched(patterns, flag):
            bad = [p for p in patterns
                   if not any(_project_matches(k, p) for k in known)]
            if bad:
                return ("%s values match no known project: %s (known: %s)"
                        % (flag, sorted(bad), sorted(known)))
            return None

        errs = [m for m in (_unmatched(includes, "-I/--include-project"),
                            _unmatched(excludes, "-X/--exclude-project"))
                if m]
        if errs:
            raise RuntimeError("; ".join(errs))

        if includes:
            candidates = {p for p in known
                          if any(_project_matches(p, i) for i in includes)}
        else:
            candidates = set(known)
        self._in_scope_projects = {p for p in candidates
                                   if not any(_project_matches(p, x) for x in excludes)}

    def _project_config(self):
        return self.context.globals.project

    def _project_root(self) -> str:
        return self._project_config().root

    def _project_state_namespace(self) -> str:
        return self._project_config().state_namespace

    def _project_cleanup_enabled(self) -> bool:
        return bool(self._project_config().cleanup)

    def _core_api(self):
        from kubernetes import client as k8s_client_module
        return k8s_client_module.CoreV1Api(self.context.k8s.client)

    def _coord_api(self):
        from kubernetes import client as k8s_client_module
        return k8s_client_module.CoordinationV1Api(self.context.k8s.client)

    def _dry_run_arg(self):
        return "All" if self.context.app.args.dry_run else None

    @_pretty_api_exc
    def _project_ensure_state_namespace(self) -> bool:
        """Ensure ``state_namespace`` exists. Return True if subsequent state
        operations (Lease, Secret) can proceed; return False on a dry-run
        invocation against a missing namespace — server-side dry-run would
        accept the namespace CREATE but not actually create it, causing every
        dependent in-namespace call to 404 confusingly.
        """
        from kubernetes import client as k8s_client_module
        from kubernetes.client.rest import ApiException

        ns = self._project_state_namespace()
        core = self._core_api()
        try:
            core.read_namespace(name=ns)
            return True
        except ApiException as e:
            if e.status != 404:
                raise
        if self.context.app.args.dry_run:
            logger.info(
                "State namespace %s does not exist; it would be created on a "
                "committed run. Skipping dry-run for Lease and state Secret to "
                "avoid a confusing validation cascade.", ns)
            return False
        logger.info("Creating state namespace %s", ns)
        body = k8s_client_module.V1Namespace(
            metadata=k8s_client_module.V1ObjectMeta(name=ns))
        try:
            core.create_namespace(body=body)
        except ApiException as e:
            if e.status == 409:
                return True  # Raced; already exists
            raise
        return True

    @_pretty_api_exc
    def _project_acquire_lease(self):
        """Acquire a per-root Lease in ``state_namespace``. Fail fast on a
        live lease; take over a stale one using resourceVersion precondition.
        """
        from kubernetes import client as k8s_client_module
        from kubernetes.client.rest import ApiException

        if self.context.app.args.dry_run:
            logger.info("Skipping Lease acquisition in dry-run mode")
            return

        self._project_lease_identity = _lease_identity()
        lease_name = _lease_name(self._project_root())
        ns = self._project_state_namespace()
        coord = self._coord_api()

        for _ in range(PROJECT_LEASE_ACQUIRE_ATTEMPTS):
            try:
                current = coord.read_namespaced_lease(name=lease_name, namespace=ns)
            except ApiException as e:
                if e.status != 404:
                    raise
                current = None

            now = datetime.now(timezone.utc)
            if current is None:
                body = k8s_client_module.V1Lease(
                    metadata=k8s_client_module.V1ObjectMeta(name=lease_name, namespace=ns),
                    spec=k8s_client_module.V1LeaseSpec(
                        holder_identity=self._project_lease_identity,
                        lease_duration_seconds=PROJECT_LEASE_DURATION_SECONDS,
                        acquire_time=now,
                        renew_time=now,
                    ),
                )
                try:
                    coord.create_namespaced_lease(namespace=ns, body=body)
                except ApiException as e:
                    if e.status == 409:
                        continue  # Raced — re-read next iteration
                    raise
                self._project_lease_acquired = True
                logger.info("Acquired project Lease %s in %s as %s",
                            lease_name, ns, self._project_lease_identity)
                return

            spec = current.spec
            holder = spec.holder_identity or "<unknown>"
            duration = spec.lease_duration_seconds or PROJECT_LEASE_DURATION_SECONDS
            renew = spec.renew_time or spec.acquire_time
            if renew is not None and renew.tzinfo is None:
                renew = renew.replace(tzinfo=timezone.utc)
            expiry = (renew + timedelta(seconds=duration)) if renew else now
            if expiry >= now:
                raise RuntimeError(
                    "Lease %s in %s is held by %r (expires %s); "
                    "another kubernator run is active. Retry later."
                    % (lease_name, ns, holder, expiry.isoformat()))
            logger.warning("Lease %s is stale (holder=%r, expired at %s); taking over",
                           lease_name, holder, expiry.isoformat())
            current.spec.holder_identity = self._project_lease_identity
            current.spec.lease_duration_seconds = PROJECT_LEASE_DURATION_SECONDS
            current.spec.acquire_time = now
            current.spec.renew_time = now
            try:
                coord.replace_namespaced_lease(
                    name=lease_name, namespace=ns, body=current)
                self._project_lease_acquired = True
                logger.info("Took over stale Lease %s in %s as %s",
                            lease_name, ns, self._project_lease_identity)
                return
            except ApiException as e:
                if e.status == 409:
                    continue  # resourceVersion precondition failed — retry
                raise
        raise RuntimeError(
            "Failed to acquire Lease %s in %s after %d attempts"
            % (lease_name, ns, PROJECT_LEASE_ACQUIRE_ATTEMPTS))

    def _project_renew_loop(self):
        """Greenlet body: every ``RENEW_INTERVAL_SECONDS``, bump the Lease's
        renewTime. On any failure mode that indicates lost ownership, sets
        ``_project_lease_abort`` so the main greenlet can notice."""
        from kubernetes.client.rest import ApiException

        lease_name = _lease_name(self._project_root())
        ns = self._project_state_namespace()
        coord = self._coord_api()

        while True:
            gevent.sleep(PROJECT_LEASE_RENEW_INTERVAL_SECONDS)
            try:
                current = coord.read_namespaced_lease(name=lease_name, namespace=ns)
            except ApiException as e:
                api_exc_normalize_body(e)
                api_exc_format_body(e)
                logger.error("Lease %s renewal read failed: %s", lease_name, e)
                self._project_lease_abort = True
                return
            if (current.spec.holder_identity or "") != self._project_lease_identity:
                logger.error("Lease %s identity mismatch (expected %r, got %r); aborting",
                             lease_name, self._project_lease_identity,
                             current.spec.holder_identity)
                self._project_lease_abort = True
                return
            current.spec.renew_time = datetime.now(timezone.utc)
            try:
                coord.replace_namespaced_lease(
                    name=lease_name, namespace=ns, body=current)
                logger.debug("Renewed Lease %s", lease_name)
            except ApiException as e:
                api_exc_normalize_body(e)
                api_exc_format_body(e)
                logger.error("Lease %s renewal replace failed (%s); aborting", lease_name, e)
                self._project_lease_abort = True
                return

    def _project_start_renewal(self):
        if not self._project_lease_acquired:
            return
        self._project_lease_renewer = gevent.spawn(self._project_renew_loop)

    def _project_stop_renewal(self):
        g = self._project_lease_renewer
        self._project_lease_renewer = None
        if g is not None and not g.dead:
            g.kill(block=False)

    def _project_release_lease(self):
        from kubernetes.client.rest import ApiException

        if not self._project_lease_acquired:
            return
        lease_name = _lease_name(self._project_root())
        ns = self._project_state_namespace()
        coord = self._coord_api()
        try:
            coord.delete_namespaced_lease(name=lease_name, namespace=ns)
            logger.info("Released project Lease %s", lease_name)
        except ApiException as e:
            if e.status == 404:
                logger.debug("Lease %s already gone on release", lease_name)
            else:
                api_exc_normalize_body(e)
                api_exc_format_body(e)
                logger.warning("Failed to delete Lease %s: %s", lease_name, e)
        finally:
            self._project_lease_acquired = False

    def _project_check_renewal(self):
        if self._project_lease_abort:
            raise RuntimeError(
                "Project Lease was lost during run (renewal failure). Aborting to "
                "avoid clobbering another run's state.")

    # --- State Secret I/O --------------------------------------------------

    @_pretty_api_exc
    def _project_read_prior_state(self):
        from kubernetes.client.rest import ApiException

        ns = self._project_state_namespace()
        root = self._project_root()
        name = _state_secret_name(root)
        core = self._core_api()
        try:
            secret = core.read_namespaced_secret(name=name, namespace=ns)
        except ApiException as e:
            if e.status != 404:
                raise
            logger.info("No prior project state Secret %s — baseline will be recorded this run", name)
            self._project_prior_state = _empty_state_payload()
            self._project_state_rv = None
            return
        self._project_state_rv = secret.metadata.resource_version
        data = secret.data or {}
        encoded = data.get(PROJECT_STATE_SECRET_DATA_KEY)
        if not encoded:
            logger.warning("Project state Secret %s is missing key %r — treating as baseline",
                           name, PROJECT_STATE_SECRET_DATA_KEY)
            self._project_prior_state = _empty_state_payload()
            return
        try:
            payload = _decode_state(encoded)
        except Exception as e:
            raise RuntimeError(
                "Failed to decode project state Secret %s: %s" % (name, e)) from e
        if payload.get(_STATE_VERSION) != PROJECT_STATE_VERSION:
            raise RuntimeError(
                "Project state Secret %s has unsupported version %r (expected %r)"
                % (name, payload.get(_STATE_VERSION), PROJECT_STATE_VERSION))
        if not payload.get(_STATE_FINALIZED, True):
            logger.warning(
                "Project state Secret %s was not finalized by the previous run "
                "(pending=%s). The prior run may have crashed; cleanup will "
                "conservatively consider both resources and pending.",
                name, sorted(payload.get(_STATE_PENDING, {}).keys()))
        self._project_prior_state = payload

    def _project_compute_new_intent(self):
        """Group current in-scope resources by project, as sorted ident lists.

        Returns a dict mapping sub-project name → sorted list of ident dicts,
        plus the set of currently-annotated projects (for cleanup diff)."""
        current = {}
        for r in self.resources.values():
            p = r.project
            if not p:
                continue
            current.setdefault(p, []).append(_resource_ident(r))
        # Apply scope filter (if active) to restrict what gets recorded.
        if self._in_scope_projects is not None:
            current = {p: v for p, v in current.items() if p in self._in_scope_projects}
        # Sort each project's idents for stable Secret content across runs.
        for p in current:
            current[p].sort(key=_ident_key)
        return current

    def _project_merge_resources(self, prior_resources: dict, new_intent: dict) -> dict:
        """Return the finalized ``resources`` map: in-scope sub-projects come
        from ``new_intent``; out-of-scope sub-projects are preserved verbatim."""
        merged = {
            p: list(idents) for p, idents in prior_resources.items()
            if self._in_scope_projects is not None and p not in self._in_scope_projects
        }
        for p, idents in new_intent.items():
            merged[p] = list(idents)
        return merged

    @_pretty_api_exc
    def _project_write_state(self, payload: dict):
        """Create or replace the state Secret. Uses the cached ``resource_version``
        from the initial read (or prior write) so we don't re-GET every time;
        falls back to a fresh read on a 409 precondition failure."""
        from kubernetes import client as k8s_client_module
        from kubernetes.client.rest import ApiException

        ns = self._project_state_namespace()
        root = self._project_root()
        name = _state_secret_name(root)
        core = self._core_api()
        encoded = _encode_state(payload)
        dry_run = self._dry_run_arg()
        common_kwargs = {"dry_run": dry_run} if dry_run else {}

        def _body(rv):
            meta = k8s_client_module.V1ObjectMeta(
                name=name, namespace=ns,
                annotations={PROJECT_ROOT_ANNOTATION: root})
            if rv is not None:
                meta.resource_version = rv
            return k8s_client_module.V1Secret(
                metadata=meta,
                type=PROJECT_STATE_SECRET_TYPE,
                data={PROJECT_STATE_SECRET_DATA_KEY: encoded},
            )

        if self._project_state_rv is None:
            # Prior read returned 404 — create. Handle 409 (raced create) by
            # falling through to the replace branch.
            try:
                resp = core.create_namespaced_secret(
                    namespace=ns, body=_body(None), **common_kwargs)
                self._project_state_rv = resp.metadata.resource_version
                logger.debug("Created project state Secret %s (%d bytes payload)",
                             name, len(encoded))
                return
            except ApiException as e:
                if e.status != 409:
                    raise
                # Re-read to pick up the winner's resourceVersion.
                existing = core.read_namespaced_secret(name=name, namespace=ns)
                self._project_state_rv = existing.metadata.resource_version

        try:
            resp = core.replace_namespaced_secret(
                name=name, namespace=ns,
                body=_body(self._project_state_rv),
                **common_kwargs)
        except ApiException as e:
            if e.status != 409:
                raise
            # Our cached resourceVersion is stale; re-read once and retry.
            existing = core.read_namespaced_secret(name=name, namespace=ns)
            self._project_state_rv = existing.metadata.resource_version
            resp = core.replace_namespaced_secret(
                name=name, namespace=ns,
                body=_body(self._project_state_rv),
                **common_kwargs)
        self._project_state_rv = resp.metadata.resource_version
        logger.debug("Replaced project state Secret %s (%d bytes payload)",
                     name, len(encoded))

    def _project_write_pre_apply(self):
        """Phase 1: record ``pending=new_intent`` with ``finalized=false`` while
        keeping ``resources=prior_resources``. A crash before the Finalize
        write leaves both visible so the next run's conservative union of
        ``resources`` and ``pending`` still picks up everything we owned."""
        self._project_new_intent = self._project_compute_new_intent()
        payload = {
            _STATE_VERSION: PROJECT_STATE_VERSION,
            _STATE_FINALIZED: False,
            _STATE_RESOURCES: dict(self._project_prior_state.get(_STATE_RESOURCES, {})),
            _STATE_PENDING: self._project_new_intent,
        }
        self._project_write_state(payload)

    def _project_write_finalize(self):
        prior_resources = self._project_prior_state.get(_STATE_RESOURCES, {})
        merged_resources = self._project_merge_resources(
            prior_resources, self._project_new_intent or {})
        payload = {
            _STATE_VERSION: PROJECT_STATE_VERSION,
            _STATE_FINALIZED: True,
            _STATE_RESOURCES: merged_resources,
            _STATE_PENDING: {},
        }
        self._project_write_state(payload)

    def _project_compute_obsolete(self) -> list:
        prior_resources = self._project_prior_state.get(_STATE_RESOURCES, {})
        prior_pending = self._project_prior_state.get(_STATE_PENDING, {})
        prior_finalized = self._project_prior_state.get(_STATE_FINALIZED, True)

        prior_projects = set(prior_resources.keys())
        if not prior_finalized:
            prior_projects |= set(prior_pending.keys())

        current_in_scope_keys = {
            _ident_key(ident)
            for idents in (self._project_new_intent or {}).values()
            for ident in idents
        }

        prior_in_scope_keys = {}
        for p in prior_projects:
            if self._in_scope_projects is not None and p not in self._in_scope_projects:
                continue
            for ident in prior_resources.get(p, []):
                prior_in_scope_keys[_ident_key(ident)] = ident
            if not prior_finalized:
                for ident in prior_pending.get(p, []):
                    prior_in_scope_keys.setdefault(_ident_key(ident), ident)

        to_delete = [ident for key, ident in prior_in_scope_keys.items()
                     if key not in current_in_scope_keys]
        to_delete.sort(key=_ident_key)
        return to_delete

    def _project_delete_obsolete(self):
        """Delete the resources that used to be ours but are no longer in
        scope. Accumulates errors — the run fails after best-effort deletion
        so the Finalize write is skipped and the next run retries."""
        from kubernetes.client.rest import ApiException

        to_delete = self._project_compute_obsolete()
        if not to_delete:
            return
        dry_run = self.context.app.args.dry_run
        cleanup_enabled = self._project_cleanup_enabled()
        if not cleanup_enabled:
            preview = ["%s/%s/%s%s" % (i.get("group") or "core",
                                       i["kind"], i["name"],
                                       "." + i["namespace"] if i.get("namespace") else "")
                       for i in to_delete]
            logger.info(
                "Project cleanup is disabled — %d obsolete resource(s) would be deleted "
                "if cleanup=True: %s",
                len(to_delete), preview)
            return

        failures = []
        for ident in to_delete:
            group = ident.get("group") or ""
            version = ident.get("version") or "v1"
            api_version = "%s/%s" % (group, version) if group else version
            manifest = {
                "apiVersion": api_version,
                "kind": ident["kind"],
                "metadata": {"name": ident["name"]},
            }
            if ident.get("namespace"):
                manifest["metadata"]["namespace"] = ident["namespace"]
            try:
                res = self.resource(manifest)
            except Exception as e:
                logger.critical("Cannot resolve resource for cleanup %s: %s", ident, e)
                failures.append((ident, e))
                continue
            try:
                logger.info("Cleanup: deleting obsolete resource %s%s",
                            res, " (dry run)" if dry_run else "")
                res.delete(dry_run=dry_run, wait=False)
            except ApiException as e:
                if e.status == 404:
                    logger.debug("Cleanup: %s already gone", res)
                    continue
                # res.delete is decorated with _normalize_api_exc upstream —
                # body is already parsed; re-format for pretty output.
                api_exc_format_body(e)
                logger.critical("Cleanup: failed to delete %s: %s", res, e)
                failures.append((ident, e))
        if failures:
            raise RuntimeError(
                "Project cleanup failed to delete %d resource(s); see CRITICAL log lines "
                "above. Secret left with finalized=false — next run will retry." %
                (len(failures),))

    def api_remove_transformer(self, transformer):
        if transformer in self._transformers:
            self._transformers.remove(transformer)

    def api_remove_validator(self, validator):
        if validator in self._validators:
            self._validators.remove(validator)

    def api_validation_error(self, msg, *args):
        frame = sys._getframe().f_back
        tb = None
        while True:
            if not frame:
                break
            tb = types.TracebackType(tb, frame, frame.f_lasti, frame.f_lineno)
            frame = frame.f_back
        return ValueError((msg % args) if args else msg).with_traceback(tb)

    def _patch_manifest(self,
                        manifest: dict,
                        resource_description: str):
        for patcher in reversed(self._manifest_patchers):
            logger.debug("Applying patcher %s to %s",
                         getattr(patcher, "__name__", patcher),
                         resource_description)
            manifest = patcher(manifest, resource_description) or manifest

        return manifest

    def _transform_resource(self, resources: Sequence[K8SResource], resource: K8SResource) -> K8SResource:
        for transformer in reversed(self._transformers):
            logger.debug("Applying transformer %s to %s from %s",
                         getattr(transformer, "__name__", transformer),
                         resource, resource.source)
            resource = transformer(resources, resource) or resource

        return resource

    def _validate_resources(self):
        errors: list[Exception] = []
        for resource in self.resources.values():
            for validator in reversed(self._validators):
                logger.debug("Applying validator %s to %s from %s",
                             getattr(validator, "__name__", validator),
                             resource, resource.source)
                errors.extend(validator(self.resources, resource, self.api_validation_error))
        if errors:
            for error in errors:
                logger.error("Validation error: %s", error)
            raise errors[0]

    def _apply_resource(self,
                        dry_run,
                        patch_field_excludes: Iterable[re.compile],
                        resource: K8SResource,
                        patch_func: Callable[[Iterable[dict]], Optional[dict]],
                        create_func: Callable[[], Optional[dict]],
                        delete_func: Callable[[K8SPropagationPolicy], None],
                        status_msg):
        from kubernetes import client
        from kubernetes.client.rest import ApiException

        rdef = resource.rdef
        rdef.populate_api(client, self.context.k8s.client)

        def handle_400_strict_validation_error(e: ApiException):
            if e.status == 400:
                # Assumes the body has been parsed
                status = e.body
                if status["status"] == "Failure":
                    if FIELD_VALIDATION_STRICT_MARKER in status["message"]:
                        message = status["message"]
                        messages = message[message.find(FIELD_VALIDATION_STRICT_MARKER) +
                                           len(FIELD_VALIDATION_STRICT_MARKER):].split(",")
                        for m in messages:
                            self._api_warnings(resource, m.strip())

                        raise e from None
                    else:
                        logger.error("FAILED MODIFYING resource %s from %s: %s",
                                     resource, resource.source, status["message"])
                        raise e from None

        def create(exists_ok=False):
            logger.info("Creating resource %s%s%s", resource, status_msg,
                        " (ignoring existing)" if exists_ok else "")
            try:
                return create_func()
            except ApiException as __e:
                if exists_ok and __e.status == 409 and __e.body["reason"] == "AlreadyExists":
                    return None
                raise

        merge_instrs, normalized_manifest = extract_merge_instructions(resource.manifest, resource)
        if merge_instrs:
            logger.trace("Normalized manifest (no merge instructions) for resource %s: %s", resource,
                         normalized_manifest)
        else:
            normalized_manifest = resource.manifest

        logger.debug("Applying resource %s%s", resource, status_msg)
        try:
            remote_resource = resource.get()
            logger.trace("Current resource %s: %s", resource, remote_resource)
            # v3 evaluates transition rules here (oldSelf bound to the
            # server's current state). v2 has no transition rules and
            # the resource was already schema-validated at add_resource
            # time, so skip a second pass.
            if self.validator.version == "v3":
                transition_errors = list(
                    self.validator.iter_errors(resource.manifest, resource.rdef,
                                               old_manifest=remote_resource))
                if transition_errors:
                    for err in transition_errors:
                        logger.error("Transition rule violation on %s from %s: %s",
                                     resource, resource.source, err)
                    raise transition_errors[0]
        except ApiException as e:
            try:
                if e.status == 404:
                    try:
                        return 1, 0, 0, create()
                    except ApiException as e:
                        if not handle_400_strict_validation_error(e):
                            raise
                else:
                    raise
            except ApiException as _e:
                api_exc_format_body(_e)
                raise
        else:
            while True:
                logger.trace("Attempting to retrieve a normalized patch for resource %s: %s",
                             resource, normalized_manifest)
                try:
                    merged_resource = resource.patch(normalized_manifest,
                                                     patch_type=K8SResourcePatchType.SERVER_SIDE_PATCH,
                                                     dry_run=True,
                                                     force=True)
                except ApiException as e:
                    try:
                        if e.status == 422:
                            status = e.body
                            # Assumes the body has been unmarshalled
                            details = status["details"]
                            immutable_key = details.get("group"), details["kind"]

                            try:
                                propagation_policy = self.context.k8s.immutable_changes[immutable_key]
                            except KeyError:
                                raise e from None
                            else:
                                for cause in details["causes"]:
                                    if (
                                            cause["reason"] == "FieldValueInvalid" and
                                            "field is immutable" in cause["message"]
                                            or
                                            cause["reason"] == "FieldValueForbidden" and
                                            ("Forbidden: updates to" in cause["message"]
                                             or
                                             "Forbidden: pod updates" in cause["message"])
                                    ):
                                        logger.info("Deleting resource %s (cascade %s)%s", resource,
                                                    propagation_policy.policy,
                                                    status_msg)
                                        delete_func(propagation_policy=propagation_policy)
                                        return 1, 0, 1, create(exists_ok=dry_run)
                                raise
                        else:
                            if not handle_400_strict_validation_error(e):
                                raise
                    except ApiException as _e:
                        api_exc_format_body(_e)
                        raise

                else:
                    logger.trace("Merged resource %s: %s", resource, merged_resource)
                    if merge_instrs:
                        apply_merge_instructions(merge_instrs, normalized_manifest, merged_resource, logger, resource)

                    patch = jsonpatch.make_patch(remote_resource, merged_resource)

                    resource_version = merged_resource["metadata"]["resourceVersion"]
                    resource_uid = merged_resource["metadata"]["uid"]
                    logger.trace("Resource %s adding resourceVersion %s and UID %s tests", resource, resource_version,
                                 resource_uid)
                    patch.patch.append({"op": "test", "path": "/metadata/uid", "value": resource_uid})
                    patch.patch.append({"op": "test", "path": "/metadata/resourceVersion", "value": resource_version})

                    logger.trace("Resource %s initial patches are: %s", resource, patch)
                    patch = self._filter_resource_patch(patch, patch_field_excludes)
                    logger.trace("Resource %s final patches are: %s", resource, patch)
                    if patch:
                        logger.info("Patching resource %s%s", resource, status_msg)
                        try:
                            return 0, 1, 0, patch_func(patch)
                        except ApiException as e:
                            if e.status == 409:
                                logger.warning("Patching resource %s%s encountered a conflict - will retry: \n%s",
                                               resource, status_msg, yaml.dump(e.body))
                                continue
                            raise
                    else:
                        logger.info("Nothing to patch for resource %s", resource)
                        return 0, 0, 0, None

    def _filter_resource_patch(self, patch: Iterable[Mapping], excludes: Iterable[re.compile]):
        result = []
        for op in patch:
            if op["op"] != "test":
                path = op["path"]
                excluded = False
                for exclude in excludes:
                    if exclude.match(path):
                        logger.trace("Excluding %r from patch %s", op, patch)
                        excluded = True
                        break
                if excluded:
                    continue
            result.append(op)
        return result

    def _setup_k8s_client(self):
        from kubernetes import client
        from kubernetes.config import load_incluster_config, load_kube_config, ConfigException

        try:
            logger.debug("Trying K8S in-cluster configuration")
            load_incluster_config()
            logger.info("Running K8S with in-cluster configuration")
        except ConfigException as e:
            logger.trace("K8S in-cluster configuration failed", exc_info=e)
            logger.debug("Initializing K8S with kubeconfig configuration")
            load_kube_config(config_file=self.context.kubeconfig.kubeconfig)

        k8s_client = client.ApiClient()

        # Patch the header content type selector to allow json patch
        k8s_client._select_header_content_type = k8s_client.select_header_content_type
        k8s_client.select_header_content_type = self._select_header_content_type_patch

        return k8s_client

    def _select_header_content_type_patch(self, content_types):
        """Returns `Content-Type` based on an array of content_types provided.
        :param content_types: List of content-types.
        :return: Content-Type (e.g. application/json).
        """

        content_type = self.context.k8s.client._select_header_content_type(content_types)
        if content_type == "application/merge-patch+json":
            return "application/json-patch+json"
        return content_type

    def __repr__(self):
        return "Kubernetes Plugin"
