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

from gevent.monkey import patch_all, is_anything_patched

if not is_anything_patched():
    patch_all()

import logging
import unittest
import json
from kubernator.api import jp
from pathlib import Path

TRACE = 5


def trace(self, msg, *args, **kwargs):
    """
    Log 'msg % args' with severity 'TRACE'.

    To pass exception information, use the keyword argument exc_info with
    a true value, e.g.

    logger.trace("Houston, we have a %s", "interesting problem", exc_info=1)
    """
    if self.isEnabledFor(TRACE):
        self._log(TRACE, msg, args, **kwargs)


logging.addLevelName(5, "TRACE")
logging.Logger.trace = trace


class JsonPathTestsTestcase(unittest.TestCase):
    def test_jp(self):
        with open(Path(__file__).parent / "deployment.json", "rb") as f:
            deployment = json.load(f)

        # if (r.group == "apps" and r.kind in ("StatefulSet", "Deployment", "DaemonSet")
        #        and "envFrom" in r.manifest["spec"]["template"]["spec"]["containers"][0]
        #        and "annotations" in r.manifest["spec"]["template"]["metadata"]
        #        and "backend_app" in r.manifest["spec"]["template"]["metadata"]["annotations"]):
        #    configmap_name = r.manifest["spec"]["template"]["spec"]["containers"][0]["envFrom"][0]["configMapRef"][
        #        "name"]
        #    configmap_namespace = r.manifest["metadata"]["namespace"]

        self.assertEqual(jp("$.spec.template.spec.containers[*].envFrom[*].configMapRef.name").only(deployment),
                         "user-api")
        self.assertEqual(jp("$.spec.template.metadata.annotations.backend_app").first(deployment),
                         "backend_app")
        self.assertIsNone(jp("$.spec.template.metadata.annotations.will_not_find_this_annotation").first(deployment))
        self.assertEqual(len(jp("$.spec.template.spec.containers[*]").all(deployment)), 1)
