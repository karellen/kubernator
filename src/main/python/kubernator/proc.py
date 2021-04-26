# -*- coding: utf-8 -*-
#
# Copyright 2021 © Payperless
#


import logging
import os
from collections.abc import Callable
from functools import partial
from io import BytesIO
from subprocess import Popen, PIPE, DEVNULL, CalledProcessError, TimeoutExpired
from typing import Union, IO, BinaryIO, TextIO, AnyStr, Iterable

from gevent import spawn, Timeout

from kubernator.api import StringIO

__all__ = ["run"]

logger = logging.getLogger("kubernator.proc")


def stream_writer_buf(pipe: BinaryIO, source_func):
    for buf in source_func():
        pipe.write(buf)


def stream_writer_line(pipe: TextIO, source_func):
    pipe.writelines(source_func())


def stream_reader_buf(pipe: BinaryIO, sink_func):
    buf = bytearray(16384)
    while read := pipe.readinto(buf):
        sink_func(memoryview(buf)[:read])


def stream_reader_line(pipe: TextIO, sink_func):
    for line in pipe:
        sink_func(line)


class ProcessRunner:
    def __init__(self, args,
                 stdout: Union[None, int, IO, Callable[[AnyStr], None]],
                 stderr: Union[None, int, IO, Callable[[AnyStr], None]],
                 stdin: Union[None, int, IO, Callable[[], Iterable[AnyStr]]] = DEVNULL,
                 *,
                 safe_args=None, universal_newlines=True, **kwargs):
        self._safe_args = safe_args or args
        logger.trace("Starting %r", self._safe_args)
        self._proc = Popen(args,
                           stdout=PIPE if isinstance(stdout, Callable) else (stdout if stdout is not None else DEVNULL),
                           stderr=PIPE if isinstance(stderr, Callable) else (stderr if stderr is not None else DEVNULL),
                           stdin=PIPE if isinstance(stderr, Callable) else (stdin if stdin is not None else DEVNULL),
                           universal_newlines=universal_newlines,
                           env=os.environ if "env" not in kwargs else kwargs["env"],
                           **kwargs)

        self._stdout_reader = spawn(partial(stream_reader_line if universal_newlines else stream_reader_buf,
                                            self._proc.stdout, stdout)) if isinstance(stdout, Callable) else None
        self._stderr_reader = spawn(partial(stream_reader_line if universal_newlines else stream_reader_buf,
                                            self._proc.stderr, stderr)) if isinstance(stderr, Callable) else None
        self._stdin_writer = spawn(partial(stream_writer_line if universal_newlines else stream_writer_buf,
                                           self._proc.stdin, stdin)) if isinstance(stdin, Callable) else None

    @property
    def stdout(self):
        if not self._stdout_reader:
            raise RuntimeError("not available")
        return self._proc.stdout

    @property
    def stderr(self):
        if not self._stderr_reader:
            raise RuntimeError("not available")
        return self._proc.stderr

    @property
    def stdin(self):
        if not self._stdin_writer:
            raise RuntimeError("not available")
        return self._proc.stdin

    def wait(self, fail=True, timeout=None):
        with Timeout(timeout, TimeoutExpired):
            retcode = self._proc.wait()
            if self._stdin_writer:
                self._stdin_writer.join()
            if self._stdout_reader:
                self._stdout_reader.join()
            if self._stderr_reader:
                self._stderr_reader.join()
        if fail and retcode:
            raise CalledProcessError(retcode, self._safe_args)
        return retcode

    def terminate(self):
        self._proc.terminate()

    def kill(self):
        self._proc.kill()


run = ProcessRunner


def run_capturing_out(args, stderr_logger, stdin=DEVNULL, *, safe_args=None, universal_newlines=True, **kwargs):
    out = StringIO(trimmed=False) if universal_newlines else BytesIO()
    proc = run(args, out.write, stderr_logger, stdin, safe_args=safe_args, universal_newlines=universal_newlines,
               **kwargs)
    proc.wait()
    return out.getvalue()
