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
import sys
import unittest

from kubernator.proc import run_capturing_out, DEVNULL, CalledProcessError

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


class ProcTestcase(unittest.TestCase):
    def test_proc_stdin(self):
        self.assertEqual(run_capturing_out([sys.executable, "-c", "import sys; print(sys.stdin.read())"],
                                           DEVNULL,
                                           "Hello world"
                                           ), "Hello world\n")

    def test_proc_output_with_failure(self):
        try:
            run_capturing_out([sys.executable, "-c", "import sys; print('Hello World'); sys.exit(1)"],
                              DEVNULL,
                              )
            self.assertFalse(True, "Should not have gotten here")
        except CalledProcessError as e:
            self.assertEqual(e.output, "Hello World\n")
