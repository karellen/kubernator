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

import json
import logging
import urllib.parse
from typing import Mapping, Optional

from kubernator.api import FileType, load_remote_file

logger = logging.getLogger("kubernator.k8s_schema.sources")


GITHUB_V3_LIST_URL = (
    "https://api.github.com/repos/kubernetes/kubernetes/contents/"
    "api/openapi-spec/v3?ref={ref}"
)
GITHUB_V3_RAW_URL = (
    "https://raw.githubusercontent.com/kubernetes/kubernetes/"
    "{ref}/api/openapi-spec/v3/{name}"
)


def _gv_path_to_filename(gv_path: str) -> str:
    """`api/v1` -> `api__v1_openapi.json`,
    `apis/apps/v1` -> `apis__apps__v1_openapi.json`.
    """
    return gv_path.replace("/", "__") + "_openapi.json"


def _filename_to_gv_path(filename: str) -> Optional[str]:
    """Inverse of :func:`_gv_path_to_filename`. Returns ``None`` for files
    whose names don't conform to the expected pattern."""
    if not filename.endswith("_openapi.json"):
        return None
    base = filename[:-len("_openapi.json")]
    return base.replace("__", "/")


class ClusterSource:
    """Fetches the OpenAPI v3 discovery index and per-group documents
    directly from a Kubernetes cluster via the embedded ``ApiClient``.

    The discovery endpoint is ``/openapi/v3``; sub-documents are referenced
    by their ``serverRelativeURL`` (which embeds a content hash, so
    in-memory caching is sufficient).
    """

    name = "cluster"

    def __init__(self, api_client):
        self.api_client = api_client

    def fetch_index(self) -> Mapping[str, str]:
        resp = self.api_client.call_api(
            resource_path="/openapi/v3",
            method="GET",
            auth_settings=["BearerToken"],
            _preload_content=False,
            _return_http_data_only=True,
        )
        data = json.loads(resp.data)
        return {gv_path: entry["serverRelativeURL"]
                for gv_path, entry in data["paths"].items()}

    def fetch_document(self, key: str, locator: str) -> Mapping:
        # locator is the serverRelativeURL — split into path/query for call_api.
        parsed = urllib.parse.urlsplit(locator)
        query_params = urllib.parse.parse_qsl(parsed.query)
        resp = self.api_client.call_api(
            resource_path=parsed.path,
            method="GET",
            query_params=query_params,
            auth_settings=["BearerToken"],
            _preload_content=False,
            _return_http_data_only=True,
        )
        return json.loads(resp.data)


class GitHubSource:
    """Fetches OpenAPI v3 documents from kubernetes/kubernetes on GitHub
    at the cluster's git tag. Used as a fallback when the cluster's
    discovery endpoint is unavailable."""

    name = "github"

    def __init__(self, git_version: str):
        # git_version is the leading-`v` form (e.g. ``v1.30.2``)
        self.git_version = git_version

    def fetch_index(self) -> Mapping[str, str]:
        listing_url = GITHUB_V3_LIST_URL.format(ref=self.git_version)
        listing = load_remote_file(logger, listing_url, FileType.JSON,
                                   sub_category="openapi_v3_index")
        # GitHub returns either a list of dicts or a single dict
        entries = listing if isinstance(listing, list) else [listing]
        index: dict[str, str] = {}
        for entry in entries:
            name = entry.get("name")
            if not name:
                continue
            gv_path = _filename_to_gv_path(name)
            if gv_path is None:
                continue
            index[gv_path] = name
        return index

    def fetch_document(self, key: str, locator: str) -> Mapping:
        url = GITHUB_V3_RAW_URL.format(ref=self.git_version, name=locator)
        return load_remote_file(logger, url, FileType.JSON,
                                sub_category="openapi_v3")
