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

import sys
from os import chdir, getcwd
from runpy import run_module
from unittest import TestCase


class IntegrationTestSupport(TestCase):

    def smoke_test_module(self, module, *args):
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
