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

import json
import unittest
from unittest.mock import MagicMock, patch

from kubernator.plugins.k8s_schema.sources import (
    ClusterSource,
    GitHubSource,
    _filename_to_gv_path,
    _gv_path_to_filename,
)


class FilenameConversionTest(unittest.TestCase):
    def test_core_round_trip(self):
        path = "api/v1"
        filename = _gv_path_to_filename(path)
        self.assertEqual(filename, "api__v1_openapi.json")
        self.assertEqual(_filename_to_gv_path(filename), path)

    def test_grouped_round_trip(self):
        path = "apis/apps/v1"
        filename = _gv_path_to_filename(path)
        self.assertEqual(filename, "apis__apps__v1_openapi.json")
        self.assertEqual(_filename_to_gv_path(filename), path)

    def test_filename_to_gv_path_non_conforming(self):
        self.assertIsNone(_filename_to_gv_path("README.md"))
        self.assertIsNone(_filename_to_gv_path("random.json"))


class ClusterSourceTest(unittest.TestCase):
    def _make(self):
        client = MagicMock()
        return ClusterSource(client), client

    def test_fetch_index(self):
        src, client = self._make()
        resp = MagicMock()
        resp.data = json.dumps({"paths": {
            "api/v1": {"serverRelativeURL": "/openapi/v3/api/v1?hash=aaa"},
            "apis/apps/v1": {"serverRelativeURL": "/openapi/v3/apis/apps/v1?hash=bbb"},
        }}).encode()
        client.call_api.return_value = resp
        index = src.fetch_index()
        self.assertEqual(index["api/v1"], "/openapi/v3/api/v1?hash=aaa")
        self.assertEqual(index["apis/apps/v1"], "/openapi/v3/apis/apps/v1?hash=bbb")
        client.call_api.assert_called_once()

    def test_fetch_document(self):
        src, client = self._make()
        doc = {"components": {"schemas": {}}, "paths": {}}
        resp = MagicMock()
        resp.data = json.dumps(doc).encode()
        client.call_api.return_value = resp
        result = src.fetch_document("api/v1", "/openapi/v3/api/v1?hash=aaa")
        self.assertEqual(result, doc)
        call_kwargs = client.call_api.call_args
        self.assertIn("query_params", call_kwargs.kwargs)

    def test_fetch_document_preserves_query_params(self):
        src, client = self._make()
        resp = MagicMock()
        resp.data = b'{"components":{}}'
        client.call_api.return_value = resp
        src.fetch_document("api/v1", "/openapi/v3/api/v1?hash=aaa&foo=bar")
        call_kwargs = client.call_api.call_args
        query = dict(call_kwargs.kwargs["query_params"])
        self.assertIn("hash", query)
        self.assertIn("foo", query)


class GitHubSourceTest(unittest.TestCase):
    def test_fetch_index(self):
        src = GitHubSource("v1.30.2")
        listing = [
            {"name": "api__v1_openapi.json"},
            {"name": "apis__apps__v1_openapi.json"},
            {"name": "README.md"},
            {"name": ""},
        ]
        with patch("kubernator.plugins.k8s_schema.sources.load_remote_file",
                   return_value=listing):
            index = src.fetch_index()
        self.assertIn("api/v1", index)
        self.assertIn("apis/apps/v1", index)
        self.assertEqual(len(index), 2)

    def test_fetch_index_single_dict(self):
        src = GitHubSource("v1.30.2")
        listing = {"name": "api__v1_openapi.json"}
        with patch("kubernator.plugins.k8s_schema.sources.load_remote_file",
                   return_value=listing):
            index = src.fetch_index()
        self.assertEqual(index, {"api/v1": "api__v1_openapi.json"})

    def test_fetch_document(self):
        src = GitHubSource("v1.30.2")
        doc = {"components": {"schemas": {}}}
        with patch("kubernator.plugins.k8s_schema.sources.load_remote_file",
                   return_value=doc):
            result = src.fetch_document("api/v1", "api__v1_openapi.json")
        self.assertEqual(result, doc)


if __name__ == "__main__":
    unittest.main()
