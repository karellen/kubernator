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


import json
import logging
import re
import sys
import types
from collections.abc import Mapping
from functools import partial
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Iterable, Callable, Sequence

import jsonpatch
import yaml

from kubernator.api import (KubernatorPlugin,
                            Globs,
                            scan_dir,
                            load_file,
                            FileType,
                            load_remote_file,
                            StripNL,
                            install_python_k8s_client)
from kubernator.plugins.k8s_api import (K8SResourcePluginMixin,
                                        K8SResource,
                                        K8SResourcePatchType,
                                        K8SPropagationPolicy)

logger = logging.getLogger("kubernator.k8s")
proc_logger = logger.getChild("proc")
stdout_logger = StripNL(proc_logger.info)
stderr_logger = StripNL(proc_logger.warning)

FIELD_VALIDATION_STRICT_MARKER = "strict decoding error: "
VALID_FIELD_VALIDATION = ("Ignore", "Warn", "Strict")


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


class KubernetesPlugin(KubernatorPlugin, K8SResourcePluginMixin):
    logger = logger

    _name = "k8s"

    def __init__(self):
        super().__init__()
        self.context = None

        self.embedded_pkg_version = self._get_kubernetes_client_version()

        self._transformers = []
        self._validators = []

    def set_context(self, context):
        self.context = context

    def register(self, field_validation="Strict", field_validation_warn_fatal=True):
        self.context.app.register_plugin("kubeconfig")

        if field_validation not in VALID_FIELD_VALIDATION:
            raise ValueError("'field_validation' must be one of %s" % (", ".join(VALID_FIELD_VALIDATION)))

        context = self.context
        context.globals.k8s = dict(patch_field_excludes=("^/metadata/managedFields",
                                                         "^/metadata/generation",
                                                         "^/metadata/creationTimestamp",
                                                         "^/metadata/resourceVersion",
                                                         ),
                                   immutable_changes={("apps", "DaemonSet"): K8SPropagationPolicy.BACKGROUND,
                                                      ("apps", "StatefulSet"): K8SPropagationPolicy.ORPHAN,
                                                      ("apps", "Deployment"): K8SPropagationPolicy.ORPHAN,
                                                      ("storage.k8s.io", "StorageClass"): K8SPropagationPolicy.ORPHAN,
                                                      },
                                   default_includes=Globs(["*.yaml", "*.yml"], True),
                                   default_excludes=Globs([".*"], True),
                                   add_resources=self.add_resources,
                                   load_resources=self.api_load_resources,
                                   load_remote_resources=self.api_load_remote_resources,
                                   load_crds=self.api_load_crds,
                                   load_remote_crds=self.api_load_remote_crds,
                                   add_transformer=self.api_add_transformer,
                                   remove_transformer=self.api_remove_transformer,
                                   add_validator=self.api_remove_validator,
                                   get_api_versions=self.get_api_versions,
                                   create_resource=self.create_resource,
                                   field_validation=field_validation,
                                   field_validation_warn_fatal=field_validation_warn_fatal,
                                   field_validation_warnings=0,
                                   _k8s=self,
                                   )
        context.k8s = dict(default_includes=Globs(context.globals.k8s.default_includes),
                           default_excludes=Globs(context.globals.k8s.default_excludes)
                           )
        self.api_add_validator(final_resource_validator)

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
        pkg_major = self.embedded_pkg_version[0]
        if server_minor != pkg_major:
            logger.info("Bundled Kubernetes client version %s doesn't match server version %s",
                        ".".join(self.embedded_pkg_version), ".".join(k8s.server_version))
            pkg_dir = install_python_k8s_client(self.context.app.run, server_minor, stdout_logger, stderr_logger)

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
        else:
            logger.info("Bundled Kubernetes client version %s matches server version %s",
                        ".".join(self.embedded_pkg_version), ".".join(k8s.server_version))

        logger.debug("Reading Kubernetes OpenAPI spec for %s", k8s.server_git_version)

        k8s_def = load_remote_file(logger, f"https://raw.githubusercontent.com/kubernetes/kubernetes/"
                                           f"{k8s.server_git_version}/api/openapi-spec/swagger.json",
                                   FileType.JSON)
        self.resource_definitions_schema = k8s_def

        self._populate_resource_definitions()

    def _setup_client(self):
        from kubernetes import client

        context = self.context
        k8s = context.k8s

        k8s.client = self._setup_k8s_client()
        version = client.VersionApi(k8s.client).get_code()
        if "-eks-" in version.git_version:
            git_version = version.git_version.split("-")[0]
        else:
            git_version = version.git_version

        k8s.server_version = git_version[1:].split(".")
        k8s.server_git_version = git_version

        logger.info("Found Kubernetes %s on %s", k8s.server_git_version, k8s.client.configuration.host)
        K8SResource._k8s_client_version = tuple(map(int, pkg_version("kubernetes").split(".")))
        K8SResource._k8s_field_validation = k8s.field_validation
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

            manifests = load_file(logger, p, FileType.YAML, display_p)

            for manifest in manifests:
                if manifest:
                    self.add_resource(manifest, display_p)

    def handle_apply(self):
        context = self.context
        k8s = context.k8s

        self._validate_resources()

        cmd = context.app.args.command
        file = context.app.args.file
        file_format = context.app.args.output_format
        dry_run = context.app.args.dry_run
        dump = cmd == "dump"

        status_msg = f"{' (dump only)' if dump else ' (dry run)' if dry_run else ''}"
        if dump:
            logger.info("Will dump the changes into a file %s in %s format", file, file_format)

        patch_field_excludes = [re.compile(e) for e in context.globals.k8s.patch_field_excludes]
        dump_results = []
        for resource in self.resources.values():
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

                def create_func():
                    method_descriptor = {"method": "create",
                                         "body": resource.manifest}
                    dump_results.append(method_descriptor)

                def delete_func(*, propagation_policy):
                    method_descriptor = {"method": "delete",
                                         "resource": resource_id,
                                         "propagation_policy": propagation_policy.policy
                                         }
                    dump_results.append(method_descriptor)
            else:
                patch_func = partial(resource.patch, patch_type=K8SResourcePatchType.JSON_PATCH, dry_run=dry_run)
                create_func = partial(resource.create, dry_run=dry_run)
                delete_func = partial(resource.delete, dry_run=dry_run)

            self._apply_resource(dry_run,
                                 patch_field_excludes,
                                 resource,
                                 patch_func,
                                 create_func,
                                 delete_func,
                                 status_msg)

        if ((dump or dry_run) and
                k8s.field_validation_warn_fatal and self.context.globals.k8s.field_validation_warnings):
            msg = ("There were %d field validation warnings and the warnings are fatal!" %
                   self.context.globals.k8s.field_validation_warnings)
            logger.fatal(msg)
            raise RuntimeError(msg)

        if dump:
            if file_format in ("json", "json-pretty"):
                json.dump(dump_results, file, sort_keys=True,
                          indent=4 if file_format == "json-pretty" else None)
            else:
                yaml.safe_dump(dump_results, file)

    def api_load_resources(self, path: Path, file_type: str):
        return self.add_local_resources(path, FileType[file_type.upper()])

    def api_load_remote_resources(self, url: str, file_type: str, file_category=None):
        return self.add_remote_resources(url, FileType[file_type.upper()], sub_category=file_category)

    def api_load_crds(self, path: Path, file_type: str):
        return self.add_local_crds(path, FileType[file_type.upper()])

    def api_load_remote_crds(self, url: str, file_type: str, file_category=None):
        return self.add_remote_crds(url, FileType[file_type.upper()], sub_category=file_category)

    def api_add_transformer(self, transformer):
        if transformer not in self._transformers:
            self._transformers.append(transformer)

    def api_add_validator(self, validator):
        if validator not in self._validators:
            self._validators.append(validator)

    def api_remove_transformer(self, transformer):
        if transformer in self._transformers:
            self._transformers.remove(transformer)

    def api_remove_validator(self, validator):
        if validator not in self._validators:
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
                        patch_func: Callable[[Iterable[dict]], None],
                        create_func: Callable[[], None],
                        delete_func: Callable[[K8SPropagationPolicy], None],
                        status_msg):
        from kubernetes import client
        from kubernetes.client.rest import ApiException

        rdef = resource.rdef
        rdef.populate_api(client, self.context.k8s.client)

        def handle_400_strict_validation_error(e: ApiException):
            if e.status == 400:
                status = json.loads(e.body)

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
                create_func()
            except ApiException as e:
                if exists_ok:
                    if e.status == 409:
                        status = json.loads(e.body)
                        if status["reason"] == "AlreadyExists":
                            return
                raise

        logger.debug("Applying resource %s%s", resource, status_msg)
        try:
            remote_resource = resource.get()
            logger.trace("Current resource %s: %s", resource, remote_resource)
        except ApiException as e:
            if e.status == 404:
                try:
                    create()
                except ApiException as e:
                    if not handle_400_strict_validation_error(e):
                        raise

            else:
                raise
        else:
            logger.trace("Attempting to retrieve a normalized patch for resource %s: %s", resource, resource.manifest)
            try:
                merged_resource = resource.patch(resource.manifest,
                                                 patch_type=K8SResourcePatchType.SERVER_SIDE_PATCH,
                                                 dry_run=True,
                                                 force=True)
            except ApiException as e:
                if e.status == 422:
                    status = json.loads(e.body)
                    details = status["details"]
                    immutable_key = details["group"], details["kind"]

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
                                    "Forbidden: updates to" in cause["message"]
                            ):
                                logger.info("Deleting resource %s (cascade %s)%s", resource,
                                            propagation_policy.policy,
                                            status_msg)
                                delete_func(propagation_policy=propagation_policy)
                                create(exists_ok=dry_run)
                                return
                        raise
                else:
                    if not handle_400_strict_validation_error(e):
                        raise
            else:
                logger.trace("Merged resource %s: %s", resource, merged_resource)
                patch = jsonpatch.make_patch(remote_resource, merged_resource)
                logger.trace("Resource %s initial patches are: %s", resource, patch)
                patch = self._filter_resource_patch(patch, patch_field_excludes)
                logger.trace("Resource %s final patches are: %s", resource, patch)
                if patch:
                    logger.info("Patching resource %s%s", resource, status_msg)
                    patch_func(patch)
                else:
                    logger.info("Nothing to patch for resource %s", resource)

    def _filter_resource_patch(self, patch: Iterable[Mapping], excludes: Iterable[re.compile]):
        result = []
        for op in patch:
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
