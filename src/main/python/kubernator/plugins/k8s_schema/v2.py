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

import logging
from collections.abc import Iterable, Iterator, Mapping, MutableMapping
from typing import Optional

from jsonschema._keywords import required
from jsonschema.exceptions import ValidationError
from jsonschema.validators import extend
# Why OAS31Validator (not OAS30) for Kubernetes swagger.json:
# K8s swagger.json has hundreds of `$ref` nodes with sibling keywords
# (mostly `description`, plus `x-kubernetes-*` extensions and the
# `JSONSchemaProps` meta-def). OpenAPI 3.0 mandates ignoring siblings
# on `$ref`, which OAS30Validator enforces and which destroys those
# docs. JSON Schema 2020-12 / OpenAPI 3.1 honors `$ref` siblings, so
# OAS31Validator is the only viable base for v2 swagger validation.
from openapi_schema_validator import OAS31Validator

from kubernator.api import FileType, load_remote_file
from kubernator.plugins.k8s_api import (K8SResourceDef,
                                        K8SResourceDefKey,
                                        to_group_and_version)
from kubernator.plugins.k8s_schema.base import (OpenAPIValidator,
                                                extract_gvk_keys,
                                                k8s_format_checker,
                                                type_validator)

logger = logging.getLogger("kubernator.k8s_schema.v2")


K8SValidator = extend(OAS31Validator, validators={
    "type": type_validator,
    "required": required
})


class SwaggerV2Validator(OpenAPIValidator):
    """Loads Kubernetes OpenAPI v2 (swagger.json) from GitHub and validates
    manifests against it. Preserves the pre-refactor behavior."""

    version = "v2"

    def __init__(self, context):
        self.context = context
        self.resource_definitions: MutableMapping[K8SResourceDefKey, K8SResourceDef] = {}
        self.resource_paths: MutableMapping[K8SResourceDefKey, MutableMapping[str, dict]] = {}
        self.resource_definitions_schema: Optional[Mapping] = None

    def load(self) -> None:
        k8s = self.context.k8s
        logger.debug("Reading Kubernetes OpenAPI v2 spec for %s", k8s.server_git_version)
        k8s_def = load_remote_file(
            logger,
            f"https://raw.githubusercontent.com/kubernetes/kubernetes/"
            f"{k8s.server_git_version}/api/openapi-spec/swagger.json",
            FileType.JSON)
        self.resource_definitions_schema = k8s_def
        self._populate_resource_definitions()

    def iter_errors(
            self,
            manifest: Mapping,
            rdef: K8SResourceDef,
            *,
            old_manifest: Optional[Mapping] = None,
    ) -> Iterator[ValidationError]:
        # old_manifest is accepted for API parity with v3 (transition rules);
        # v2 built-in schemas carry no x-kubernetes-validations so it's ignored.
        validator = K8SValidator(rdef.schema, format_checker=k8s_format_checker)
        yield from validator.iter_errors(manifest)

    def api_versions(self) -> Iterable[str]:
        api_versions: set[str] = set()
        for key in self.resource_definitions:
            api_version = f"{f'{key.group}/' if key.group else ''}{key.version}"
            api_versions.add(api_version)
        return sorted(api_versions)

    def _populate_resource_definitions(self) -> None:
        k8s_def = self.resource_definitions_schema
        paths = k8s_def["paths"]
        for path, actions in paths.items():
            path_rdk = None
            path_actions: list[str] = []
            for action, action_details in actions.items():
                if action == "parameters":
                    continue
                rdks = list(extract_gvk_keys(action_details))
                if rdks:
                    assert len(rdks) == 1
                    rdk = rdks[0]
                    if path_rdk:
                        if path_rdk != rdk:
                            raise ValueError(
                                f"Encountered path action x-kubernetes-group-version-kind conflict: "
                                f"{path}: {actions}")
                        path_actions.append(action_details["x-kubernetes-action"])
                    else:
                        path_rdk = rdk

            if path_rdk:
                rdef_paths = self.resource_paths.setdefault(path_rdk, {})
                rdef_paths[path] = actions

        for k, schema in k8s_def["definitions"].items():
            # short-circuit ref resolution to the top of the document
            schema["definitions"] = k8s_def["definitions"]
            for key in extract_gvk_keys(schema):
                for rdef in K8SResourceDef.from_manifest(key, schema, self.resource_paths):
                    self.resource_definitions[key] = rdef


# re-export for factory/consumer convenience
__all__ = [
    "SwaggerV2Validator",
    "K8SValidator",
    "to_group_and_version",
]
