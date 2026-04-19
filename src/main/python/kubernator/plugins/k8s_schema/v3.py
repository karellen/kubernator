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
import re
from collections.abc import Iterable, Iterator, Mapping, MutableMapping
from typing import Any, Optional

from jsonschema._keywords import required
from jsonschema.exceptions import ValidationError
from jsonschema.validators import extend
from openapi_schema_validator import OAS30Validator

from kubernator.plugins.k8s_api import (K8SResourceDef,
                                        K8SResourceDefKey,
                                        to_group_and_version)
from kubernator.plugins.k8s_schema.base import (OpenAPIValidator,
                                                extract_gvk_keys,
                                                k8s_format_checker,
                                                type_validator)
from kubernator.plugins.k8s_schema.cel import CELEvaluator

logger = logging.getLogger("kubernator.k8s_schema.v3")


# Matches OpenAPI v3 group-version-path keys published by Kubernetes:
#   api/v1
#   apis/<group>/<version>   (group may itself contain dots, e.g. apps,
#                             apiextensions.k8s.io)
_GV_PATH_RE = re.compile(r"^(api|apis/[^/]+)/[^/]+$")


def _gv_path_to_api_version(gv_path: str) -> Optional[str]:
    """``api/v1`` → ``v1``, ``apis/apps/v1`` → ``apps/v1``."""
    if gv_path.startswith("api/"):
        return gv_path[len("api/"):]
    if gv_path.startswith("apis/"):
        return gv_path[len("apis/"):]
    return None


def _api_version_to_gv_path(api_version: str) -> str:
    if "/" not in api_version:
        return f"api/{api_version}"
    return f"apis/{api_version}"


def _ref_name(ref: str) -> Optional[str]:
    if not isinstance(ref, str):
        return None
    if ref.startswith("#/components/schemas/"):
        return ref[len("#/components/schemas/"):]
    return None


def _walk_refs(schema: Any) -> Iterator[str]:
    if isinstance(schema, Mapping):
        if "$ref" in schema:
            name = _ref_name(schema["$ref"])
            if name:
                yield name
        for v in schema.values():
            yield from _walk_refs(v)
    elif isinstance(schema, list):
        for v in schema:
            yield from _walk_refs(v)


def _owning_gv_paths(ref_name: str, index_keys: Iterable[str]) -> list[str]:
    """Map a ``$ref`` name (e.g. ``io.k8s.api.apps.v1.Deployment``) back to
    the group-version path(s) that could hold it, using the discovery
    index as a ground-truth enumeration."""
    index_list = list(index_keys)

    if ref_name.startswith("io.k8s.api.core.v1."):
        return ["api/v1"]

    if ref_name.startswith("io.k8s.api."):
        parts = ref_name[len("io.k8s.api."):].split(".")
        # "<group-parts>.<version>.<Kind>": version and Kind are the last two.
        if len(parts) >= 3:
            version = parts[-2]
            group_parts = parts[:-2]
            group = ".".join(group_parts)
            candidate = f"apis/{group}/{version}"
            if candidate in index_list:
                return [candidate]

    # apimachinery and any ref we can't pin down: probe the entire index
    # in a stable order (core first, then alphabetical). The fetcher will
    # merge whichever document contains the definition.
    ordered = []
    if "api/v1" in index_list:
        ordered.append("api/v1")
    for p in sorted(index_list):
        if p == "api/v1":
            continue
        ordered.append(p)
    return ordered


# ---------------------------------------------------------------------------
# Custom keyword handlers for Kubernetes extensions
# ---------------------------------------------------------------------------

_orig_additional_properties = OAS30Validator.VALIDATORS["additionalProperties"]


def _hashable(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((k, _hashable(v)) for k, v in value.items()))
    if isinstance(value, list):
        return tuple(_hashable(v) for v in value)
    return value


def list_type_validator(validator, list_type, instance, schema):
    if list_type == "atomic":
        return
    if not isinstance(instance, list):
        return
    if list_type == "set":
        seen: set = set()
        for idx, item in enumerate(instance):
            key = _hashable(item)
            if key in seen:
                yield ValidationError(
                    f"item at index {idx} duplicates an earlier item "
                    f"(x-kubernetes-list-type: set)")
                continue
            seen.add(key)
        return
    if list_type == "map":
        keys = schema.get("x-kubernetes-list-map-keys") or []
        if not keys:
            return
        seen_keys: set = set()
        for idx, item in enumerate(instance):
            if not isinstance(item, dict):
                yield ValidationError(
                    f"item at index {idx} is not an object "
                    f"(x-kubernetes-list-type: map requires object items)")
                continue
            missing = [k for k in keys if k not in item]
            if missing:
                yield ValidationError(
                    f"item at index {idx} is missing x-kubernetes-list-map "
                    f"key(s) {missing}")
                continue
            key_tuple = tuple(_hashable(item[k]) for k in keys)
            if key_tuple in seen_keys:
                yield ValidationError(
                    f"item at index {idx} duplicates map keys {keys} of an "
                    f"earlier item")
                continue
            seen_keys.add(key_tuple)


def additional_properties_validator(validator, ap, instance, schema):
    if schema.get("x-kubernetes-preserve-unknown-fields") is True:
        return
    if schema.get("x-kubernetes-embedded-resource") is True:
        return
    yield from _orig_additional_properties(validator, ap, instance, schema)


def preserve_unknown_fields_validator(validator, flag, instance, schema):
    # The actual effect lives in additional_properties_validator above;
    # this handler exists so the keyword is recognized (not "unknown").
    return
    yield  # pragma: no cover — keep generator contract


def embedded_resource_validator(validator, flag, instance, schema):
    if flag is not True:
        return
    if not isinstance(instance, dict):
        yield ValidationError(
            "x-kubernetes-embedded-resource expects an object")
        return
    if "apiVersion" not in instance:
        yield ValidationError("embedded resource is missing 'apiVersion'")
    if "kind" not in instance:
        yield ValidationError("embedded resource is missing 'kind'")
    metadata = instance.get("metadata")
    if isinstance(metadata, dict):
        name = metadata.get("name")
        if name is not None:
            from kubernator.plugins.k8s_schema.cel.extensions.format_lib import (
                _check_dns1123_subdomain,
            )
            errs = _check_dns1123_subdomain(str(name))
            for e in errs:
                yield ValidationError(f"embedded resource metadata.name {e}")


V3ValidatorCls = extend(OAS30Validator, validators={
    "type": type_validator,
    "required": required,
    "x-kubernetes-list-type": list_type_validator,
    "additionalProperties": additional_properties_validator,
    "x-kubernetes-preserve-unknown-fields": preserve_unknown_fields_validator,
    "x-kubernetes-embedded-resource": embedded_resource_validator,
})


# ---------------------------------------------------------------------------
# Lazy resource-definitions map
# ---------------------------------------------------------------------------


class _LazyResourceDefinitions(MutableMapping):
    """Dict-like mapping whose missed lookups trigger *load_group* for the
    key's (group, version)."""

    def __init__(self, load_group):
        self._load_group = load_group
        self._data: dict[K8SResourceDefKey, K8SResourceDef] = {}

    def __getitem__(self, key: K8SResourceDefKey) -> K8SResourceDef:
        try:
            return self._data[key]
        except KeyError:
            pass
        self._load_group(key.group, key.version)
        return self._data[key]

    def __setitem__(self, key: K8SResourceDefKey, value: K8SResourceDef):
        self._data[key] = value

    def __delitem__(self, key: K8SResourceDefKey):
        del self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class OpenAPIV3Validator(OpenAPIValidator):
    """OpenAPI v3 validator with lazy per-group fetch, transitive ``$ref``
    resolution across group documents, K8s extension enforcement, and
    CEL rule evaluation."""

    version = "v3"

    def __init__(self, context, sources: list):
        self.context = context
        self.sources = list(sources)
        self.resource_definitions = _LazyResourceDefinitions(self._ensure_group_loaded)
        self.resource_paths: MutableMapping[K8SResourceDefKey, MutableMapping[str, dict]] = {}

        self._index: dict[str, str] = {}
        self._active_source = None
        self._loaded_groups: set[str] = set()
        self._scanned_for_refs: set[str] = set()
        self._components_schemas: dict[str, dict] = {}
        self._injected_schema_cache: dict[int, dict] = {}
        self._cel_evaluator = CELEvaluator()

    # ------------------------------------------------------------------ load

    def load(self) -> None:
        errors: list[Exception] = []
        for source in self.sources:
            try:
                logger.debug("Fetching OpenAPI v3 index via %s", source.name)
                self._index = dict(source.fetch_index())
                self._active_source = source
                logger.info("Loaded OpenAPI v3 discovery index (%d group-versions) "
                            "via %s", len(self._index), source.name)
                return
            except Exception as e:  # noqa: BLE001
                logger.warning("OpenAPI v3 index fetch via %s failed: %s",
                               source.name, e)
                errors.append(e)
        raise RuntimeError(
            "Failed to fetch OpenAPI v3 discovery index from any configured source"
        ) from (errors[-1] if errors else None)

    # ------------------------------------------------------------------ api

    def api_versions(self) -> Iterable[str]:
        """Reads from the discovery index directly — no sub-document fetch."""
        out: set[str] = set()
        for gv_path in self._index:
            api_version = _gv_path_to_api_version(gv_path)
            if api_version is not None:
                out.add(api_version)
        return sorted(out)

    def iter_errors(self,
                    manifest: Mapping,
                    rdef: K8SResourceDef,
                    *,
                    old_manifest: Optional[Mapping] = None,
                    ) -> Iterator[ValidationError]:
        schema = self._inject_components(rdef.schema)
        validator = V3ValidatorCls(schema, format_checker=k8s_format_checker)
        yield from validator.iter_errors(manifest)
        yield from self._cel_evaluator.iter_rule_errors(
            manifest, rdef.schema, old_manifest=old_manifest)

    # ------------------------------------------------------------------ lazy fetch

    def _ensure_group_loaded(self, group: str, version: str) -> None:
        api_version = f"{group}/{version}" if group else version
        gv_path = _api_version_to_gv_path(api_version)
        if gv_path in self._loaded_groups:
            return
        if gv_path not in self._index:
            raise KeyError(f"Kubernetes group {api_version!r} not found in OpenAPI v3 "
                           f"discovery index")
        self._populate_group(gv_path)

    def _populate_group(self, gv_path: str) -> None:
        if self._active_source is None:
            raise RuntimeError("OpenAPIV3Validator.load() was not called")
        locator = self._index[gv_path]
        logger.debug("Loading OpenAPI v3 document %s via %s",
                     gv_path, self._active_source.name)
        document = self._active_source.fetch_document(gv_path, locator)
        self._loaded_groups.add(gv_path)

        components = document.get("components") or {}
        schemas = components.get("schemas") or {}
        self._components_schemas.update(schemas)

        paths = document.get("paths") or {}
        self._populate_from_paths(paths)
        self._populate_from_components(schemas)
        self._resolve_refs()

    def _populate_from_paths(self, paths: Mapping) -> None:
        for path, path_entry in paths.items():
            if not isinstance(path_entry, Mapping):
                continue
            path_rdk = None
            for action_details in path_entry.values():
                if not isinstance(action_details, Mapping):
                    continue
                for rdk in extract_gvk_keys(action_details):
                    if path_rdk is None:
                        path_rdk = rdk
                    elif path_rdk != rdk:
                        raise ValueError(
                            f"Encountered path action x-kubernetes-group-version-kind "
                            f"conflict: {path}: {path_entry}")
            if path_rdk:
                rdef_paths = self.resource_paths.setdefault(path_rdk, {})
                rdef_paths[path] = dict(path_entry)

    def _populate_from_components(self, schemas: Mapping) -> None:
        for schema in schemas.values():
            if not isinstance(schema, Mapping):
                continue
            for key in extract_gvk_keys(schema):
                for rdef in K8SResourceDef.from_manifest(key, dict(schema),
                                                         self.resource_paths):
                    self.resource_definitions[key] = rdef

    def _resolve_refs(self) -> None:
        """Scan schemas that haven't been walked yet for cross-document
        ``$ref``s, pull their owning groups from the discovery index,
        and loop until the component graph is closed."""
        while True:
            unresolved: set[str] = set()
            pending = [name for name in self._components_schemas
                       if name not in self._scanned_for_refs]
            if not pending:
                return
            for name in pending:
                for ref in _walk_refs(self._components_schemas[name]):
                    if ref not in self._components_schemas:
                        unresolved.add(ref)
                self._scanned_for_refs.add(name)

            if not unresolved:
                return

            for ref in unresolved:
                for candidate in _owning_gv_paths(ref, self._index.keys()):
                    if candidate in self._loaded_groups:
                        continue
                    self._populate_group(candidate)
                    if ref in self._components_schemas:
                        break

    def _inject_components(self, schema: Mapping) -> dict:
        """Return a copy of *schema* with ``components.schemas`` pointing
        at the cumulative store so OAS30Validator's local ``$ref``
        resolver finds cross-document definitions. Cached per schema
        object so repeated validations on the same rdef don't re-copy."""
        cached = self._injected_schema_cache.get(id(schema))
        if cached is not None:
            return cached
        out = dict(schema)
        components = dict(out.get("components") or {})
        components["schemas"] = self._components_schemas
        out["components"] = components
        self._injected_schema_cache[id(schema)] = out
        return out


__all__ = [
    "OpenAPIV3Validator",
    "V3ValidatorCls",
    "_gv_path_to_api_version",
    "_api_version_to_gv_path",
    "_owning_gv_paths",
    "to_group_and_version",
]
