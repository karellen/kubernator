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
from unittest.mock import patch

from kubernator.api import PropertyDict
from kubernator.plugins.k8s_schema import make_validator
from kubernator.plugins.k8s_schema.sources import ClusterSource, GitHubSource
from kubernator.plugins.k8s_schema.v2 import SwaggerV2Validator


SWAGGER_FIXTURE = {
    "paths": {},
    "definitions": {
        "io.k8s.api.core.v1.ConfigMap": {
            "type": "object",
            "x-kubernetes-group-version-kind": [
                {"group": "", "version": "v1", "kind": "ConfigMap"}],
            "properties": {},
        },
    },
}


def _ctx(minor="30", *, openapi_version="auto", openapi_source="auto",
         with_client=True):
    ctx = PropertyDict()
    ctx.k8s = dict(
        server_version=["1", str(minor), "0"],
        server_git_version=f"v1.{minor}.0",
        client=object() if with_client else None,
    )
    ctx.globals = PropertyDict()
    ctx.globals.k8s = dict(
        openapi_version=openapi_version,
        openapi_source=openapi_source,
    )
    return ctx


class _FakeSource:
    def __init__(self, name, index=None, raise_on_fetch=False):
        self.name = name
        self.index = index or {"api/v1": "/openapi/v3/api/v1?h=x"}
        self.raise_on_fetch = raise_on_fetch

    def fetch_index(self):
        if self.raise_on_fetch:
            raise RuntimeError(f"{self.name} down")
        return self.index

    def fetch_document(self, *args, **kwargs):  # pragma: no cover
        return {"components": {"schemas": {}}, "paths": {}}


class FactoryTest(unittest.TestCase):
    # ---------- v3 path
    def test_auto_on_modern_server_picks_v3(self):
        ctx = _ctx(minor=30)
        with patch("kubernator.plugins.k8s_schema.OpenAPIV3Validator") as v3cls:
            instance = v3cls.return_value
            instance.load.return_value = None
            result = make_validator(ctx)
            self.assertIs(result, instance)
            instance.load.assert_called_once()

    def test_auto_on_modern_server_v3_failure_falls_back_to_v2(self):
        ctx = _ctx(minor=30)
        with patch("kubernator.plugins.k8s_schema.OpenAPIV3Validator") as v3cls, \
             patch("kubernator.plugins.k8s_schema.v2.load_remote_file",
                   return_value=SWAGGER_FIXTURE):
            v3cls.return_value.load.side_effect = RuntimeError("both sources down")
            result = make_validator(ctx)
            self.assertIsInstance(result, SwaggerV2Validator)

    def test_auto_on_legacy_server_picks_v2(self):
        ctx = _ctx(minor=26)
        with patch("kubernator.plugins.k8s_schema.OpenAPIV3Validator") as v3cls, \
             patch("kubernator.plugins.k8s_schema.v2.load_remote_file",
                   return_value=SWAGGER_FIXTURE):
            result = make_validator(ctx)
            self.assertIsInstance(result, SwaggerV2Validator)
            v3cls.assert_not_called()

    def test_forced_v3_attempts_regardless_of_gate(self):
        ctx = _ctx(minor=26, openapi_version="v3")
        with patch("kubernator.plugins.k8s_schema.OpenAPIV3Validator") as v3cls:
            v3cls.return_value.load.return_value = None
            make_validator(ctx)
            v3cls.assert_called_once()

    def test_forced_v3_cluster_failure_raises(self):
        ctx = _ctx(minor=30, openapi_version="v3", openapi_source="cluster")
        with patch("kubernator.plugins.k8s_schema.OpenAPIV3Validator") as v3cls:
            v3cls.return_value.load.side_effect = RuntimeError("nope")
            with self.assertRaises(RuntimeError):
                make_validator(ctx)

    def test_forced_v3_github_skips_cluster(self):
        ctx = _ctx(minor=30, openapi_version="v3", openapi_source="github")
        captured = {}

        class FakeV3:
            def __init__(self, context, sources):
                captured["sources"] = sources

            def load(self):
                return None

        with patch("kubernator.plugins.k8s_schema.OpenAPIV3Validator", FakeV3):
            make_validator(ctx)
        self.assertEqual(len(captured["sources"]), 1)
        self.assertIsInstance(captured["sources"][0], GitHubSource)

    def test_forced_v2_always_returns_v2(self):
        ctx = _ctx(minor=30, openapi_version="v2")
        with patch("kubernator.plugins.k8s_schema.OpenAPIV3Validator") as v3cls, \
             patch("kubernator.plugins.k8s_schema.v2.load_remote_file",
                   return_value=SWAGGER_FIXTURE):
            result = make_validator(ctx)
            self.assertIsInstance(result, SwaggerV2Validator)
            v3cls.assert_not_called()

    def test_explicit_kwarg_overrides_context(self):
        ctx = _ctx(minor=30, openapi_version="v2")
        with patch("kubernator.plugins.k8s_schema.OpenAPIV3Validator") as v3cls:
            v3cls.return_value.load.return_value = None
            make_validator(ctx, openapi_version="v3")
            v3cls.assert_called_once()

    def test_source_auto_puts_cluster_first(self):
        ctx = _ctx(minor=30)
        captured = {}

        class FakeV3:
            def __init__(self, context, sources):
                captured["sources"] = sources

            def load(self):
                return None

        with patch("kubernator.plugins.k8s_schema.OpenAPIV3Validator", FakeV3):
            make_validator(ctx)
        self.assertEqual(len(captured["sources"]), 2)
        self.assertIsInstance(captured["sources"][0], ClusterSource)
        self.assertIsInstance(captured["sources"][1], GitHubSource)

    def test_invalid_openapi_version_raises(self):
        ctx = _ctx(minor=30, openapi_version="v4")
        with self.assertRaises(ValueError):
            make_validator(ctx)

    def test_invalid_openapi_source_raises(self):
        ctx = _ctx(minor=30, openapi_source="s3")
        with self.assertRaises(ValueError):
            make_validator(ctx)


if __name__ == "__main__":
    unittest.main()
