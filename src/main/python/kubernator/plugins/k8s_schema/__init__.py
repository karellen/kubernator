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
"""OpenAPI validation factory for Kubernetes manifests.

Two validator implementations live side-by-side:

- :class:`SwaggerV2Validator` — fetches ``swagger.json`` from GitHub
  and validates using OAS31 over the legacy K8s OpenAPI v2 dialect.
- :class:`OpenAPIV3Validator` — cluster-first discovery of
  ``/openapi/v3`` with GitHub fallback; lazy per-group fetch; OAS30 +
  K8s extension keyword enforcement + CEL rule evaluation.

Selection is resolved by :func:`make_validator` against two context
knobs (``context.globals.k8s.openapi_version`` and
``.openapi_source``) that can be overridden by explicit kwargs.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from kubernator.api import config_get
from kubernator.plugins.k8s_schema.base import (K8S_MINIMAL_RESOURCE_SCHEMA,
                                                K8S_MINIMAL_RESOURCE_VALIDATOR,
                                                OpenAPIValidator)
from kubernator.plugins.k8s_schema.sources import ClusterSource, GitHubSource
from kubernator.plugins.k8s_schema.v2 import SwaggerV2Validator
from kubernator.plugins.k8s_schema.v3 import OpenAPIV3Validator

logger = logging.getLogger("kubernator.k8s_schema")


VERSION_GATE_MINOR = 27  # OpenAPI v3 GA milestone (Kubernetes 1.27)


def _server_minor(context) -> Optional[int]:
    try:
        minor = context.k8s.server_version[1]
    except (AttributeError, IndexError, KeyError):
        return None
    try:
        return int(minor)
    except (TypeError, ValueError):
        return None


def _resolve(context, *, openapi_version: str, openapi_source: str):
    """Return the effective (version, source) pair, honoring
    explicit kwargs over context values."""
    ctx_k8s = getattr(context, "k8s", None)
    ctx_globals = getattr(getattr(context, "globals", None), "k8s", None)

    if openapi_version == "auto":
        openapi_version = (config_get(ctx_globals, "openapi_version", "auto")
                           if ctx_globals is not None else "auto")
    if openapi_source == "auto":
        openapi_source = (config_get(ctx_globals, "openapi_source", "auto")
                          if ctx_globals is not None else "auto")

    if openapi_version not in ("auto", "v2", "v3"):
        raise ValueError(f"openapi_version must be auto|v2|v3, got {openapi_version!r}")
    if openapi_source not in ("auto", "cluster", "github"):
        raise ValueError(f"openapi_source must be auto|cluster|github, got {openapi_source!r}")

    return openapi_version, openapi_source, ctx_k8s


def _sources_for(context, openapi_source: str) -> list:
    k8s = context.k8s
    git_version = k8s.server_git_version
    api_client = getattr(k8s, "client", None)

    cluster = ClusterSource(api_client) if api_client is not None else None
    github = GitHubSource(git_version)

    if openapi_source == "cluster":
        if cluster is None:
            raise RuntimeError("openapi_source='cluster' requested but no K8s API client is available")
        return [cluster]
    if openapi_source == "github":
        return [github]
    # auto
    out = []
    if cluster is not None:
        out.append(cluster)
    out.append(github)
    return out


def make_validator(
        context,
        *,
        openapi_version: Literal["auto", "v2", "v3"] = "auto",
        openapi_source: Literal["auto", "cluster", "github"] = "auto",
) -> OpenAPIValidator:
    """Build an OpenAPI validator.

    ``openapi_version``:
        ``auto`` (default): use v3 on server ≥ 1.27, fall back to v2
        on any v3 failure; use v2 directly when server < 1.27.
        ``v3``: force v3; no version gate, no v2 fallback.
        ``v2``: always use v2.

    ``openapi_source`` (only meaningful for v3):
        ``auto``: cluster-first, GitHub fallback.
        ``cluster``: cluster only (no GitHub).
        ``github``: GitHub only (skip cluster).
    """
    openapi_version, openapi_source, _ = _resolve(
        context, openapi_version=openapi_version, openapi_source=openapi_source)

    minor = _server_minor(context)

    if openapi_version == "v2":
        return _load_v2(context)

    if openapi_version == "auto" and minor is not None and minor < VERSION_GATE_MINOR:
        logger.info("Kubernetes server is < 1.%d — using OpenAPI v2",
                    VERSION_GATE_MINOR)
        return _load_v2(context)

    if openapi_version == "v3" and minor is not None and minor < VERSION_GATE_MINOR:
        logger.warning("openapi_version='v3' forced on server < 1.%d "
                       "(OpenAPI v3 may not be available)", VERSION_GATE_MINOR)

    try:
        sources = _sources_for(context, openapi_source)
        v3 = OpenAPIV3Validator(context, sources=sources)
        v3.load()
        logger.info("Using OpenAPI v3 for Kubernetes server %s",
                    getattr(context.k8s, "server_git_version", "(unknown)"))
        return v3
    except Exception as e:  # noqa: BLE001
        if openapi_version == "v3":
            raise
        logger.warning("Falling back to OpenAPI v2: %s", e)
        return _load_v2(context)


def _load_v2(context):
    v = SwaggerV2Validator(context)
    v.load()
    return v


__all__ = [
    "K8S_MINIMAL_RESOURCE_SCHEMA",
    "K8S_MINIMAL_RESOURCE_VALIDATOR",
    "OpenAPIValidator",
    "SwaggerV2Validator",
    "OpenAPIV3Validator",
    "make_validator",
]
