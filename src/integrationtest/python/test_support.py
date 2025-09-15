# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2023 Karellen, Inc.
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

from gevent.monkey import patch_all

patch_all()

# All other imports must be below

import sys  # noqa: E402
import unittest  # noqa: E402
from os import chdir, getcwd  # noqa: E402
from runpy import run_module  # noqa: E402

__all__ = ["unittest", "IntegrationTestSupport"]


class IntegrationTestSupport(unittest.TestCase):
    K8S_TEST_VERSIONS = ["1.20.15", "1.21.14", "1.22.17",
                         "1.23.17", "1.24.17", "1.25.16",
                         "1.26.15", "1.27.16", "1.28.15",
                         "1.29.15", "1.30.14", "1.31.12",
                         "1.32.8", "1.33.4", "1.34.0"]

    def load_json_logs(self, log_file):
        decoder = json.JSONDecoder()
        with open(log_file, "rt") as f:
            buf = f.read()

        result = []
        while True:
            if not buf:
                break
            obj, idx = decoder.raw_decode(buf)
            buf = buf[idx:]
            buf = buf.lstrip()
            result.append(obj)

        return result

    def run_module_test(self, module, *args):
        old_argv = list(sys.argv)
        del sys.argv[:]
        sys.argv.append("bogus")
        sys.argv.extend(args)

        old_modules = dict(sys.modules)
        old_meta_path = list(sys.meta_path)
        old_sys_path = list(sys.path)
        old_cwd = getcwd()
        # chdir(self.tmp_directory)
        try:
            return run_module(module, run_name="__main__")
        except SystemExit as e:
            self.assertEqual(e.code, 0, "Test did not exit successfully: %r" % e.code)
        finally:
            del sys.argv[:]
            sys.argv.extend(old_argv)

            sys.modules.clear()
            sys.modules.update(old_modules)

            del sys.meta_path[:]
            sys.meta_path.extend(old_meta_path)

            del sys.path[:]
            sys.path.extend(old_sys_path)

            chdir(old_cwd)

            from logging import shutdown, _handlerList, root

            shutdown()

            import gc
            gc.collect()
            root.handlers.clear()
            _handlerList.clear()
            gc.collect()
