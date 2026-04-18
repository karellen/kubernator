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

from __future__ import annotations

import base64
from collections.abc import Iterable, Iterator, Mapping, MutableMapping
from typing import Literal, Optional

from jsonschema._format import FormatChecker
from jsonschema.exceptions import ValidationError
from jsonschema.validators import Draft7Validator

from kubernator.plugins.k8s_api import (K8SResourceDef,
                                        K8SResourceDefKey,
                                        to_group_and_version)


K8S_MINIMAL_RESOURCE_SCHEMA = {
    "properties": {
        "apiVersion": {"type": "string"},
        "kind": {"type": "string"},
        "metadata": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "namespace": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    "type": "object",
    "required": ["apiVersion", "kind"],
}
K8S_MINIMAL_RESOURCE_VALIDATOR = Draft7Validator(K8S_MINIMAL_RESOURCE_SCHEMA)


def extract_gvk_keys(obj: Mapping) -> Iterable[K8SResourceDefKey]:
    """Yield :class:`K8SResourceDefKey` for each ``x-kubernetes-group-version-kind``
    entry on *obj*. Handles both the single-dict and list-of-dicts shapes
    that K8s OpenAPI documents use."""
    gvks = obj.get("x-kubernetes-group-version-kind")
    if not gvks:
        return
    if isinstance(gvks, Mapping):
        gvks = [gvks]
    for gvk in gvks:
        yield K8SResourceDefKey(gvk["group"], gvk["version"], gvk["kind"])


def is_integer(instance):
    # bool inherits from int, so ensure bools aren't reported as ints
    if isinstance(instance, bool):
        return False
    return isinstance(instance, int)


def is_string(instance):
    return isinstance(instance, str)


def type_validator(validator, data_type, instance, schema):
    if instance is None:
        return

    if (data_type == "string"
            and (schema.get("format") == "int-or-string"
                 or schema.get("x-kubernetes-int-or-string") is True)):
        if not (is_string(instance) or is_integer(instance)):
            yield ValidationError("%r is not of type %s" % (instance, "int-or-string"))
    elif not validator.is_type(instance, data_type):
        yield ValidationError("%r is not of type %s" % (instance, data_type))


k8s_format_checker = FormatChecker()


@k8s_format_checker.checks("int32")
def check_int32(value):
    return value is not None and (-2147483648 < value < 2147483647)


@k8s_format_checker.checks("int64")
def check_int64(value):
    return value is not None and (-9223372036854775808 < value < 9223372036854775807)


@k8s_format_checker.checks("float")
def check_float(value):
    return value is not None and (-3.4E+38 < value < +3.4E+38)


@k8s_format_checker.checks("double")
def check_double(value):
    return value is not None and (-1.7E+308 < value < +1.7E+308)


@k8s_format_checker.checks("byte", ValueError)
def check_byte(value):
    if value is None:
        return False
    base64.b64decode(value, validate=True)
    return True


@k8s_format_checker.checks("int-or-string")
def check_int_or_string(value):
    return check_int32(value) if is_integer(value) else is_string(value)


class OpenAPIValidator:
    """Concrete base class for OpenAPI-backed Kubernetes manifest validators.

    Subclasses implement :meth:`load`, :meth:`iter_errors`, and
    :meth:`api_versions`; this base supplies the manifest-level
    entry points (:meth:`iter_manifest_errors`, :meth:`get_manifest_rdef`)
    shared by v2 and v3 so the K8s plugin mixin can delegate all
    validation to the validator without caring about version or
    minimal-schema details.
    """

    version: Literal["v2", "v3"]
    resource_definitions: MutableMapping[K8SResourceDefKey, K8SResourceDef]
    resource_paths: MutableMapping[K8SResourceDefKey, Mapping[str, dict]]

    def load(self) -> None:
        raise NotImplementedError

    def iter_errors(
            self,
            manifest: Mapping,
            rdef: K8SResourceDef,
            *,
            old_manifest: Optional[Mapping] = None,
    ) -> Iterator[ValidationError]:
        raise NotImplementedError

    def api_versions(self) -> Iterable[str]:
        raise NotImplementedError

    # -- manifest-level validation shared across versions ----------------

    def get_manifest_rdef(self, manifest: Mapping) -> K8SResourceDef:
        """Resolve a manifest to its :class:`K8SResourceDef`.
        Raises :class:`ValidationError` if the kind is unknown."""
        key = K8SResourceDefKey(*to_group_and_version(manifest["apiVersion"]),
                                manifest["kind"])
        try:
            return self.resource_definitions[key]
        except KeyError:
            raise ValidationError(
                f"{key} is not a defined Kubernetes resource",
                validator=K8S_MINIMAL_RESOURCE_VALIDATOR,
                validator_value=key,
                instance=manifest,
                schema=K8S_MINIMAL_RESOURCE_SCHEMA,
            )

    def iter_manifest_errors(
            self,
            manifest: Mapping,
            *,
            old_manifest: Optional[Mapping] = None,
    ) -> Iterator[ValidationError]:
        """Validate a manifest end-to-end: minimal envelope check →
        rdef lookup → full schema (and CEL) validation."""
        sentinel: Optional[ValidationError] = None
        for err in K8S_MINIMAL_RESOURCE_VALIDATOR.iter_errors(manifest):
            sentinel = err
            yield err
        if sentinel is not None:
            return
        try:
            rdef = self.get_manifest_rdef(manifest)
        except ValidationError as e:
            yield e
            return
        yield from self.iter_errors(manifest, rdef, old_manifest=old_manifest)
