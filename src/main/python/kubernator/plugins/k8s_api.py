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
import json
import re
from collections import namedtuple
from collections.abc import Callable, Mapping, MutableMapping, Sequence, Iterable
from enum import Enum, auto
from functools import partial
from io import StringIO
from pathlib import Path
from typing import Union, Optional

import yaml
from jsonschema._format import FormatChecker
from jsonschema._types import int_types, str_types
from jsonschema._validators import required
from jsonschema.exceptions import ValidationError
from jsonschema.validators import extend, Draft7Validator, RefResolver
from openapi_schema_validator import OAS30Validator

from kubernator.api import load_file, FileType, load_remote_file, calling_frame_source

UPPER_FOLLOWED_BY_LOWER_RE = re.compile(r"(.)([A-Z][a-z]+)")
LOWER_OR_NUM_FOLLOWED_BY_UPPER_RE = re.compile(r"([a-z0-9])([A-Z])")

K8S_MINIMAL_RESOURCE_SCHEMA = {
    "properties": {
        "apiVersion": {
            "type": "string"
        },
        "kind": {
            "type": "string"
        },
        "metadata": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string"
                },
                "namespace": {
                    "type": "string"
                }
            },
            "required": ["name"]
        }
    },
    "type": "object",
    "required": ["apiVersion", "kind"]
}
K8S_MINIMAL_RESOURCE_VALIDATOR = Draft7Validator(K8S_MINIMAL_RESOURCE_SCHEMA)

CLUSTER_RESOURCE_PATH = re.compile(r"^/apis?/(?:[^/]+/){1,2}([^/]+)$")
NAMESPACED_RESOURCE_PATH = re.compile(r"^/apis?/(?:[^/]+/){1,2}namespaces/[^/]+/([^/]+)$")


class K8SResourcePatchType(Enum):
    JSON_PATCH = auto()
    SERVER_SIDE_PATCH = auto()


class K8SPropagationPolicy(Enum):
    BACKGROUND = ("Background",)
    FOREGROUND = ("Foreground",)
    ORPHAN = ("Orphan",)

    def __init__(self, policy):
        self.policy = policy


def is_integer(instance):
    # bool inherits from int, so ensure bools aren't reported as ints
    if isinstance(instance, bool):
        return False
    return isinstance(instance, int_types)


def is_string(instance):
    return isinstance(instance, str_types)


def type_validator(validator, data_type, instance, schema):
    if instance is None:
        return

    if data_type == "string" and schema.get("format") == "int-or-string":
        if not (is_string(instance) or is_integer(instance)):
            yield ValidationError("%r is not of type %s" % (instance, "int-or-string"))
    elif not validator.is_type(instance, data_type):
        yield ValidationError("%r is not of type %s" % (instance, data_type))


K8SValidator = extend(OAS30Validator, validators={
    "type": type_validator,
    "required": required
})

k8s_format_checker = FormatChecker()


@k8s_format_checker.checks("int32")
def check_int32(value):
    return -2147483648 < value < 2147483647


@k8s_format_checker.checks("int64")
def check_int64(value):
    return -9223372036854775808 < value < 9223372036854775807


@k8s_format_checker.checks("float")
def check_float(value):
    return -3.4E+38 < value < +3.4E+38


@k8s_format_checker.checks("double")
def check_double(value):
    return -1.7E+308 < value < +1.7E+308


@k8s_format_checker.checks("byte", ValueError)
def check_byte(value):
    if value is None:
        return False
    base64.b64decode(value, validate=True)
    return True


@k8s_format_checker.checks("int-or-string")
def check_int_or_string(value):
    return check_int32(value) if is_integer(value) else is_string(value)


# def make_api_version(group, version):
#    return f"{group}/{version}" if group else version


def to_group_and_version(api_version):
    group, _, version = api_version.partition("/")
    if not version:
        version = group
        group = ""
    return group, version


def to_k8s_resource_def_key(manifest):
    return K8SResourceDefKey(*to_group_and_version(manifest["apiVersion"]),
                             manifest["kind"])


class K8SResourceDefKey(namedtuple("K8SResourceDefKey", ["group", "version", "kind"])):
    __slots__ = ()

    def __str__(self):
        return f"{self.group}{'/' if self.group else '/'}{self.version}/{self.kind}"


class K8SResourceDef:
    def __init__(self, key, singular, plural, namespaced, custom, schema):
        self.key = key
        self.singular = singular
        self.plural = plural
        self.namespaced = namespaced
        self.custom = custom
        self.schema = schema

        self._api_get = None
        self._api_create = None
        self._api_patch = None
        self._api_delete = None

    @property
    def group(self) -> str:
        return self.key.group

    @property
    def version(self) -> str:
        return self.key.version

    @property
    def kind(self) -> str:
        return self.key.kind

    @property
    def has_api(self) -> bool:
        return self.custom or self.plural

    @property
    def get(self):
        return self._api_get

    @property
    def create(self):
        return self._api_create

    @property
    def patch(self):
        return self._api_patch

    @property
    def delete(self):
        return self._api_delete

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, K8SResourceDef):
            return False

        return (self.key == o.key and
                self.singular == o.singular and
                self.plural == o.plural and
                self.namespaced == o.namespaced and
                self.custom == o.custom)

    def __hash__(self) -> int:
        return self.key.__hash__()

    def __str__(self):
        return f"{self.key=}, {self.singular=}, {self.plural=}, {self.namespaced=}, {self.custom=}"

    @classmethod
    def from_manifest(cls, key: K8SResourceDefKey,
                      schema,
                      paths: Mapping[K8SResourceDefKey, Mapping[str, Mapping]]):
        singular = key.kind.lower()

        plural = None
        namespaced = False

        if singular == "namespace":
            plural = "namespaces"
        else:
            for path in paths.get(key, ()):
                if m := NAMESPACED_RESOURCE_PATH.fullmatch(path):
                    plural = m[1]
                    namespaced = True
                    break
                elif m := CLUSTER_RESOURCE_PATH.fullmatch(path):
                    plural = m[1]

        yield K8SResourceDef(key, singular, plural, namespaced, False, schema)

    @classmethod
    def from_resource(cls, resource: "K8SResource"):
        manifest = resource.manifest
        spec = manifest["spec"]
        group = spec["group"]
        names = spec["names"]
        kind = names["kind"]
        singular = names.get("singular", names["kind"].lower())
        plural = names["plural"]
        namespaced = spec["scope"] == "Namespaced"

        for version_spec in spec["versions"]:
            version = version_spec["name"]
            if resource.version == "v1":
                schema = version_spec["schema"]["openAPIV3Schema"]
            else:
                schema = spec["validation"]["openAPIV3Schema"]
            yield K8SResourceDef(K8SResourceDefKey(group, version, kind), singular, plural, namespaced, True, schema)

    def populate_api(self, k8s_client_module, k8s_client):
        if not self.has_api:
            raise RuntimeError(f"{self} has no API")

        if self._api_get:
            return

        group = self.group or "core"
        version = self.version
        kind = self.kind

        if self.custom:
            k8s_api = k8s_client_module.CustomObjectsApi(k8s_client)

            kwargs = {"group": group,
                      "version": version,
                      "plural": self.plural}
            if self.namespaced:
                self._api_get = partial(k8s_api.get_namespaced_custom_object, **kwargs)
                self._api_patch = partial(k8s_api.patch_namespaced_custom_object, **kwargs)
                self._api_create = partial(k8s_api.create_namespaced_custom_object, **kwargs)
                self._api_delete = partial(k8s_api.delete_namespaced_custom_object, **kwargs)
            else:
                self._api_get = partial(k8s_api.get_cluster_custom_object, **kwargs)
                self._api_patch = partial(k8s_api.patch_cluster_custom_object, **kwargs)
                self._api_create = partial(k8s_api.create_cluster_custom_object, **kwargs)
                self._api_delete = partial(k8s_api.delete_cluster_custom_object, **kwargs)
        else:
            # Take care for the case e.g. api_type is "apiextensions.k8s.io"
            # Only replace the last instance
            group = "".join(group.rsplit(".k8s.io", 1))

            # convert group name from DNS subdomain format to
            # python class name convention
            group = "".join(word.capitalize() for word in group.split('.'))
            fcn_to_call = f"{group}{version.capitalize()}Api"
            k8s_api = getattr(k8s_client_module, fcn_to_call)(k8s_client)

            # Replace CamelCased action_type into snake_case
            kind = UPPER_FOLLOWED_BY_LOWER_RE.sub(r"\1_\2", kind)
            kind = LOWER_OR_NUM_FOLLOWED_BY_UPPER_RE.sub(r"\1_\2", kind).lower()

            if self.namespaced:
                self._api_get = getattr(k8s_api, f"read_namespaced_{kind}")
                self._api_patch = getattr(k8s_api, f"patch_namespaced_{kind}")
                self._api_create = getattr(k8s_api, f"create_namespaced_{kind}")
                self._api_delete = getattr(k8s_api, f"delete_namespaced_{kind}")
            else:
                self._api_get = getattr(k8s_api, f"read_{kind}")
                self._api_patch = getattr(k8s_api, f"patch_{kind}")
                self._api_create = getattr(k8s_api, f"create_{kind}")
                self._api_delete = getattr(k8s_api, f"delete_{kind}")


class K8SResourceKey(namedtuple("K8SResourceKey", ["group", "kind", "name", "namespace"])):
    __slots__ = ()

    def __str__(self):
        return (f"{self.group}{'/' if self.group else 'v1/'}{self.kind}"
                f"/{self.name}{f'.{self.namespace}' if self.namespace else ''}")


class K8SResource:
    def __init__(self, manifest: dict, rdef: K8SResourceDef, source: Union[str, Path] = None):
        self.key = self.get_manifest_key(manifest)

        self.manifest = manifest
        self.rdef = rdef
        self.source = source

    @property
    def group(self) -> str:
        return self.key.group

    @property
    def version(self) -> str:
        return self.rdef.version

    @property
    def kind(self) -> str:
        return self.key.kind

    @property
    def name(self) -> str:
        return self.key.name

    @name.setter
    def name(self, value):
        self.manifest["metadata"]["name"] = value
        self.key = self.get_manifest_key(self.manifest)

    @property
    def namespace(self) -> Optional[str]:
        return self.key.namespace

    @namespace.setter
    def namespace(self, value):
        self.manifest["metadata"]["namespace"] = value
        self.key = self.get_manifest_key(self.manifest)

    @property
    def api_version(self) -> str:
        return self.manifest["apiVersion"]

    @property
    def schema(self) -> dict:
        return self.rdef.schema

    @property
    def is_crd(self):
        return self.group == "apiextensions.k8s.io" and self.kind == "CustomResourceDefinition"

    def __str__(self):
        return f"{self.api_version}/{self.kind}/{self.name}{'.' + self.namespace if self.namespace else ''}"

    def get(self):
        rdef = self.rdef
        kwargs = {"name": self.name,
                  "_preload_content": False}
        if rdef.namespaced:
            kwargs["namespace"] = self.namespace
        return json.loads(self.rdef.get(**kwargs).data)

    def create(self, dry_run=True):
        rdef = self.rdef
        kwargs = {"body": self.manifest,
                  "_preload_content": False,
                  "field_manager": "kubernator"
                  }
        if rdef.namespaced:
            kwargs["namespace"] = self.namespace
        if dry_run:
            kwargs["dry_run"] = "All"
        return json.loads(rdef.create(**kwargs).data)

    def patch(self, json_patch, *, patch_type: K8SResourcePatchType, force=False, dry_run=True):
        rdef = self.rdef
        kwargs = {"name": self.name,
                  "body": json_patch
                  if patch_type != K8SResourcePatchType.SERVER_SIDE_PATCH
                  else json.dumps(json_patch),
                  "_preload_content": False,
                  "field_manager": "kubernator",
                  }
        if patch_type == K8SResourcePatchType.SERVER_SIDE_PATCH:
            kwargs["force"] = force
        if rdef.namespaced:
            kwargs["namespace"] = self.namespace
        if dry_run:
            kwargs["dry_run"] = "All"

        def select_header_content_type_patch(content_types):
            if patch_type == K8SResourcePatchType.JSON_PATCH:
                return "application/json-patch+json"
            if patch_type == K8SResourcePatchType.SERVER_SIDE_PATCH:
                return "application/apply-patch+yaml"
            raise NotImplementedError

        if isinstance(rdef.patch, partial):
            api_client = rdef.patch.func.__self__.api_client
        else:
            api_client = rdef.patch.__self__.api_client

        old_func = api_client.select_header_content_type
        try:
            api_client.select_header_content_type = select_header_content_type_patch
            return json.loads(rdef.patch(**kwargs).data)
        finally:
            api_client.select_header_content_type = old_func

    def delete(self, *, dry_run=True, propagation_policy=K8SPropagationPolicy.BACKGROUND):
        rdef = self.rdef
        kwargs = {"name": self.name,
                  "_preload_content": False,
                  "propagation_policy": propagation_policy.policy
                  }
        if rdef.namespaced:
            kwargs["namespace"] = self.namespace
        if dry_run:
            kwargs["dry_run"] = "All"

        return json.loads(rdef.delete(**kwargs).data)

    @staticmethod
    def get_manifest_key(manifest):
        return K8SResourceKey(to_group_and_version(manifest["apiVersion"])[0],
                              manifest["kind"],
                              manifest["metadata"]["name"],
                              manifest["metadata"].get("namespace"))

    @staticmethod
    def get_manifest_description(manifest: dict, source=None):
        api_version = manifest.get("apiVersion")
        kind = manifest.get("kind")
        metadata = manifest.get("metadata")
        name = None
        namespace = None
        if metadata:
            name = metadata.get("name")
            namespace = metadata.get("namespace")
        return (f"{api_version or 'unknown'}/{kind or '<unknown>'}/"
                f"{name or '<unknown>'}{'.' + namespace if namespace else ''}")

    def __eq__(self, other):
        if not isinstance(other, K8SResource):
            return False
        return self.key == other.key and self.manifest == other.manifest


class K8SResourcePluginMixin:
    def __init__(self):
        self.resource_definitions: MutableMapping[K8SResourceDefKey, K8SResourceDef] = {}
        self.resource_paths: MutableMapping[K8SResourceDefKey, MutableMapping[str, dict]] = {}
        self.resources: MutableMapping[K8SResourceKey, K8SResource] = {}

        self.resource_definitions_schema = None

    def add_resources(self, manifests: Union[str, list, dict], source: Union[str, Path] = None):
        if not source:
            source = calling_frame_source()

        if isinstance(manifests, str):
            manifests = list(yaml.safe_load_all(StringIO(manifests)))

        if isinstance(manifests, (Mapping, dict)):
            return self.add_resource(manifests, source)
        else:
            return [self.add_resource(m, source) for m in manifests if m]

    def add_resource(self, manifest: dict, source: Union[str, Path] = None):
        if not source:
            source = calling_frame_source()
        resource = self._create_resource(manifest, source)

        try:
            trans_resource = self._transform_resource(list(self.resources.values()), resource)
        except Exception as e:
            self.logger.error("An error occurred running transformers on %s", resource, exc_info=e)
            raise

        errors = list(self._validate_resource(trans_resource.manifest, source))
        if errors:
            for error in errors:
                if source:
                    self.logger.error("Error detected in re-transformed K8S resource %s generated through %s",
                                      trans_resource, source, exc_info=error)
            raise errors[0]

        return self._add_resource(trans_resource, source)

    def add_crds(self, manifests: Union[str, list, dict], source: Union[str, Path] = None):
        if not source:
            source = calling_frame_source()

        if isinstance(manifests, str):
            manifests = list(yaml.safe_load_all(StringIO(manifests)))

        if isinstance(manifests, (Mapping, dict)):
            return self.add_crd(manifests, source)
        else:
            return [self.add_crd(m, source) for m in manifests if m]

    def add_crd(self, manifest: dict, source: Union[str, Path] = None):
        if not source:
            source = calling_frame_source()
        resource = self._create_resource(manifest, source)
        if not resource.is_crd:
            resource_description = K8SResource.get_manifest_description(manifest, source)
            raise ValueError(f"K8S manifest {resource_description} from {source} is not a CRD")

        self._add_crd(resource)
        return resource

    def create_resource(self, manifest: dict, source: Union[str, Path] = None):
        """Create K8S resource without adding it"""
        if not source:
            source = calling_frame_source()

        return self._create_resource(manifest, source)

    def add_local_resources(self, path: Path, file_type: FileType, source: str = None):
        manifests = load_file(self.logger, path, file_type)

        return [self.add_resource(m, source or path) for m in manifests if m]

    def add_remote_resources(self, url: str, file_type: FileType, *, sub_category: Optional[str] = None,
                             source: str = None):
        manifests = load_remote_file(self.logger, url, file_type, sub_category=sub_category)

        return [self.add_resource(m, source or url) for m in manifests if m]

    def add_local_crds(self, path: Path, file_type: FileType, source: str = None):
        manifests = load_file(self.logger, path, file_type)

        return [self.add_crd(m, source or path) for m in manifests if m]

    def add_remote_crds(self, url: str, file_type: FileType, *, sub_category: Optional[str] = None,
                        source: str = None):
        manifests = load_remote_file(self.logger, url, file_type, sub_category=sub_category)

        return [self.add_crd(m, source or url) for m in manifests if m]

    def get_api_versions(self):
        api_versions = set()
        for rdef in self.resource_definitions:
            api_version = f"{f'{rdef.group}/' if rdef.group else ''}{rdef.version}"
            if api_version not in api_versions:
                api_versions.add(api_version)
        return sorted(api_versions)

    def _create_resource(self, manifest: dict, source: Union[str, Path] = None):
        resource_description = K8SResource.get_manifest_description(manifest, source)
        self.logger.debug("Validating K8S manifest for %s", resource_description)

        errors = list(self._validate_resource(manifest, source))
        if errors:
            for error in errors:
                if source:
                    self.logger.error("Error detected in K8S manifest %s from %s",
                                      resource_description, source, exc_info=error)
            raise errors[0]

        rdef = self._get_manifest_rdef(manifest)
        return K8SResource(manifest, rdef, source)

    def _add_resource(self, resource: K8SResource, source):
        if resource.key in self.resources:
            existing_resource = self.resources[resource.key]
            if resource != existing_resource:
                raise ValidationError("resource %s from %s already exists and was added from %s" %
                                      (resource.key, resource.source, existing_resource.source))
            self.logger.trace("K8S resource for %s from %s is already present and is identical", resource, source)
            return existing_resource

        self.logger.info("Adding K8S resource for %s from %s", resource, source)
        self.resources[resource.key] = resource

        if resource.is_crd:
            self._add_crd(resource)

        return resource

    def _transform_resource(self,
                            resources: Sequence[K8SResource],
                            resource: K8SResource) -> K8SResource:
        return resource

    def _filter_resources(self, func: Callable[[K8SResource], bool]):
        yield from filter(func, self.resources.values())

    def _validate_resource(self, manifest: dict, source: Union[str, Path] = None):
        for error in self._yield_manifest_rdef(manifest):
            if isinstance(error, Exception):
                yield error
            else:
                rdef = error
                # schema = ChainMap(manifest, self.resource_definitions_schema)
                k8s_validator = K8SValidator(rdef.schema,
                                             format_checker=k8s_format_checker,
                                             resolver=RefResolver.from_schema(self.resource_definitions_schema))
                yield from k8s_validator.iter_errors(manifest)

    def _get_manifest_rdef(self, manifest):
        for error in self._yield_manifest_rdef(manifest):
            if isinstance(error, Exception):
                raise error
            else:
                return error

    def _yield_manifest_rdef(self, manifest):
        error = None
        for error in K8S_MINIMAL_RESOURCE_VALIDATOR.iter_errors(manifest):
            yield error

        if error:
            return

        key = K8SResourceDefKey(*to_group_and_version(manifest["apiVersion"]), manifest["kind"])

        try:
            yield self.resource_definitions[key]
        except KeyError:
            yield ValidationError("%s is not a defined Kubernetes resource" % (key,),
                                  validator=K8S_MINIMAL_RESOURCE_VALIDATOR,
                                  validator_value=key,
                                  instance=manifest,
                                  schema=K8S_MINIMAL_RESOURCE_SCHEMA)

    def _add_crd(self, resource: K8SResource):
        for crd in K8SResourceDef.from_resource(resource):
            self.logger.info("Adding K8S CRD definition %s", crd.key)
            self.resource_definitions[crd.key] = crd

    def _populate_resource_definitions(self):
        k8s_def = self.resource_definitions_schema

        def k8s_resource_def_key(v: Mapping[str, Union[list, Mapping]]) -> Iterable[K8SResourceDefKey]:
            gvks = v.get("x-kubernetes-group-version-kind")
            if gvks:
                if isinstance(gvks, Mapping):
                    gvk = gvks
                    yield K8SResourceDefKey(gvk["group"],
                                            gvk["version"],
                                            gvk["kind"])
                else:
                    for gvk in gvks:
                        yield K8SResourceDefKey(gvk["group"],
                                                gvk["version"],
                                                gvk["kind"])

        paths = k8s_def["paths"]
        for path, actions in paths.items():
            path_rdk = None
            path_actions = []
            for action, action_details in actions.items():
                if action == "parameters":
                    continue
                rdks = list(k8s_resource_def_key(action_details))
                if rdks:
                    assert len(rdks) == 1
                    rdk = rdks[0]
                    if path_rdk:
                        if path_rdk != rdk:
                            raise ValueError(f"Encountered path action x-kubernetes-group-version-kind conflict: "
                                             f"{path}: {actions}")
                        path_actions.append(action_details["x-kubernetes-action"])
                    else:
                        path_rdk = rdk

            if path_rdk:
                rdef_paths = self.resource_paths.get(path_rdk)
                if not rdef_paths:
                    rdef_paths = {}
                    self.resource_paths[path_rdk] = rdef_paths
                rdef_paths[path] = actions

        for k, schema in k8s_def["definitions"].items():
            for key in k8s_resource_def_key(schema):
                for rdef in K8SResourceDef.from_manifest(key, schema, self.resource_paths):
                    self.resource_definitions[key] = rdef
