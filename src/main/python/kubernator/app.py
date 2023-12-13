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

import argparse
import datetime
import importlib
import logging
import pkgutil
import sys
import urllib.parse
from collections import deque
from collections.abc import MutableMapping, Callable
from pathlib import Path
from typing import Optional, Union

import kubernator
from kubernator.api import (KubernatorPlugin, Globs, scan_dir, PropertyDict, config_as_dict, config_parent,
                            download_remote_file, load_remote_file, Repository, StripNL)
from kubernator.proc import run, run_capturing_out

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
logger = logging.getLogger("kubernator")


def define_arg_parse():
    parser = argparse.ArgumentParser(description="Kubernetes Provisioning Tool",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--version", action="version", version=kubernator.__version__,
                        help="print version and exit")
    parser.add_argument("--log-format", choices=["human", "json"], default="human",
                        help="whether to log for human or machine consumption")
    parser.add_argument("--log-file", type=argparse.FileType("w"), default=None,
                        help="where to log, defaults to `stderr`")
    parser.add_argument("-v", "--verbose", choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE"],
                        default="INFO", help="how verbose do you want Kubernator to be")
    parser.add_argument("-f", "--file", type=argparse.FileType("w"), default=sys.stdout,
                        help="where to generate results, if necessary")
    parser.add_argument("-o", "--output-format", choices=["json", "json-pretty", "yaml"], default="yaml",
                        help="in what format to generate results")
    parser.add_argument("-p", "--path", dest="path", default=".",
                        type=Path, help="path to start processing")
    #    parser.add_argument("--pre-start-script", default=None, type=Path,
    #                        help="location of the pre-start script")
    #    parser.add_argument("--disconnected", action="store_true", default=False,
    #                        help="do not actually connect to the target Kubernetes")
    #    parser.add_argument("--k8s-version", type=str, default=None,
    #                        help="specify a version of Kubernetes when operating in the disconnected mode")
    parser.add_argument("--yes", action="store_false", default=True, dest="dry_run",
                        help="actually make destructive changes")
    parser.add_argument("command", nargs="?", choices=["dump", "apply"], default="dump",
                        help="whether to dump the proposed changes to the output or to apply them")
    return parser


def init_logging(verbose, output_format, output_file):
    root_log = logging.root

    handler = logging.StreamHandler(output_file)
    root_log.addHandler(handler)

    if output_format == "human":
        if handler.stream.isatty():
            import coloredlogs
            fmt_cls = coloredlogs.ColoredFormatter

        else:
            fmt_cls = logging.Formatter

        def formatTime(record, datefmt=None):
            return datetime.datetime.fromtimestamp(record.created).isoformat()

        formatter = fmt_cls("%(asctime)s %(name)s %(levelname)s %(filename)s:%(lineno)d %(message)s")
        formatter.formatTime = formatTime
    else:
        import json_log_formatter

        class JSONFormatter(json_log_formatter.JSONFormatter):
            def json_record(self, message, extra, record: logging.LogRecord):
                extra = super(JSONFormatter, self).json_record(message, extra, record)
                extra["ts"] = datetime.datetime.fromtimestamp(record.created)
                extra["name"] = record.name
                extra["level"] = record.levelname
                extra["fn"] = record.filename
                extra["ln"] = record.lineno
                del extra["time"]
                return extra

        formatter = JSONFormatter()

    handler.setFormatter(formatter)
    logger.setLevel(logging._nameToLevel[verbose])


# class RepositoryPath:
#    def __init__(self, path: Path, repository: Repository = None):
#        self.path = path.absolute()
#        self.repository = repository
#
#    def __str__(self):
#        return self.repository.url_str if self.repository else ""


class App(KubernatorPlugin):
    _name = "app"

    def __init__(self, args):
        self.args = args
        path = args.path.absolute()

        global_context = PropertyDict()
        global_context.globals = global_context
        context = PropertyDict(_parent=global_context)
        context._plugins = []

        self._top_level_context = context
        self.context = context
        self._top_dir_context = PropertyDict(_parent=self.context)

        self.repos: MutableMapping[Repository, Repository] = dict()
        self.path_q: deque[tuple[PropertyDict, Path]] = deque(((self._top_dir_context, path),))

        self._new_paths: list[tuple[PropertyDict, Path]] = []

        self._cleanups = []
        self._plugin_types = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def run(self):
        logger.info("Starting Kubernator version %s", kubernator.__version__)

        self.register_plugin(self)

        while True:
            cwd = self.next()
            if not cwd:
                logger.debug("No paths left to traverse")
                break

            context = self.context

            logger.debug("Inspecting directory %s", self._display_path(cwd))
            self._run_handlers(KubernatorPlugin.handle_before_dir, False, context, None, cwd)

            if (ktor_py := (cwd / ".kubernator.py")).exists():
                self._run_handlers(KubernatorPlugin.handle_before_script, False, context, None, cwd)

                for h in self.context._plugins:
                    h.set_context(context)

                self._exec_ktor(ktor_py)

                for h in self.context._plugins:
                    h.set_context(None)

                self._run_handlers(KubernatorPlugin.handle_after_script, True, context, None, cwd)

            self._run_handlers(KubernatorPlugin.handle_after_dir, True, context, None, cwd)

        self.context = self._top_dir_context
        context = self.context

        self._run_handlers(KubernatorPlugin.handle_apply, True, context, None)

        self._run_handlers(KubernatorPlugin.handle_verify, True, context, None)

        self._run_handlers(KubernatorPlugin.handle_shutdown, True, context, None)

    def discover_plugins(self):
        importlib.invalidate_caches()
        search_path = Path(kubernator.__path__[0], "plugins")
        [importlib.import_module(name)
         for finder, name, is_pkg in
         pkgutil.iter_modules([search_path], "kubernator.plugins.")]

        for plugin in KubernatorPlugin.__subclasses__():
            if plugin._name in self._plugin_types:
                logger.warning("Plugin named %r in %r is already reserved by %r and will be ignored",
                               plugin._name,
                               plugin,
                               self._plugin_types[plugin._name])
            else:
                logger.info("Plugin %r discovered in %r", plugin._name, plugin)
                self._plugin_types[plugin._name] = plugin

    def register_plugin(self, plugin: Union[KubernatorPlugin, type, str], **kwargs):
        context = self.context
        if isinstance(plugin, str):
            try:
                plugin_obj = self._plugin_types[plugin]()
            except KeyError:
                logger.critical("No known plugin with the name %r", plugin)
                raise RuntimeError("No known plugin with the name %r" % (plugin,))
        elif isinstance(plugin, type):
            plugin_obj = plugin()
        else:
            plugin_obj = plugin

        for p in context._plugins:
            if p._name == plugin_obj._name:
                logger.info("Plugin with name %r already registered, skipping", p._name)
                return

        logger.info("Registering plugin %r via %r", plugin_obj._name, plugin_obj)

        # Register
        self._run_handlers(KubernatorPlugin.register, False, context, plugin_obj, **kwargs)

        context._plugins.append(plugin_obj)

        # Init
        self._run_handlers(KubernatorPlugin.handle_init, False, context, plugin_obj)

        # Start
        self._run_handlers(KubernatorPlugin.handle_start, False, context, plugin_obj)

        # If we're already processing a directory
        if "app" in self.context and "cwd" in self.context.app and self.context.app.cwd:
            cwd = self.context.app.cwd
            self._run_handlers(KubernatorPlugin.handle_before_dir, False, context, plugin_obj, cwd)

            # If we're already in the script (TODO: is it possible to NOT be in a script?)
            if "script" in self.context.app:
                self._run_handlers(KubernatorPlugin.handle_before_script, False, context, plugin_obj, cwd)

    def _run_handlers(self, __f, __reverse, __context, __plugin, *args, **kwargs):
        f_name = __f.__name__

        def run(h):
            h_f = getattr(h, f_name, None)
            if h_f:
                logger.trace("Running %r handler on %r with %r, %r", f_name, h, args, kwargs)
                h_f(*args, **kwargs)

        if __plugin:
            __plugin.set_context(__context)
            run(__plugin)
        else:
            self._set_plugin_context(__reverse, __context, run)

    def _set_plugin_context(self, reverse, context, run):
        for h in list(self.context._plugins if not reverse else reversed(self.context._plugins)):
            h.set_context(context)
            run(h)
            h.set_context(None)

    def _exec_ktor(self, ktor_py: Path):
        ktor_py_display_path = self._display_path(ktor_py)
        logger.debug("Executing %s", ktor_py_display_path)
        with open(ktor_py, "rb") as f:
            source = f.read()
        co = compile(source, ktor_py_display_path, "exec")
        globs = {"ktor": self.context,
                 "logger": logger.getChild("script")
                 }
        exec(co, globs)
        logger.debug("Executed %r", ktor_py_display_path)

    def next(self) -> Path:
        path_queue: deque[tuple[PropertyDict, Path]] = self.path_q
        if path_queue:
            self.context, path = path_queue.pop()
            return path

    def register_cleanup(self, h):
        if not hasattr(h, "cleanup"):
            raise RuntimeError("cleanup handler has no cleanup attribute")
        self._cleanups.append(h)

    def cleanup(self):
        for h in self._cleanups:
            h.cleanup()

    def register(self, **kwargs):
        self.discover_plugins()

    def handle_init(self):
        context = self.context

        context.globals.common = dict()
        context.globals.app = dict(display_path=self._display_path,
                                   args=self.args,
                                   repository_credentials_provider=self._repository_credentials_provider,
                                   walk_remote=self.walk_remote,
                                   walk_local=self.walk_local,
                                   register_plugin=self.register_plugin,
                                   config_as_dict=config_as_dict,
                                   config_parent=config_parent,
                                   download_remote_file=download_remote_file,
                                   load_remote_file=load_remote_file,
                                   register_cleanup=self.register_cleanup,
                                   run=self._run,
                                   run_capturing_out=self._run_capturing_out,
                                   repository=self.repository,
                                   StripNL=StripNL,
                                   default_includes=Globs(["*"], True),
                                   default_excludes=Globs([".*"], True),
                                   )
        context.app = dict(_repository_credentials_provider=None,
                           default_includes=Globs(context.app.default_includes),
                           default_excludes=Globs(context.app.default_excludes),
                           includes=Globs(context.app.default_includes),
                           excludes=Globs(context.app.default_excludes),
                           )

    def handle_before_dir(self, cwd: Path):
        context = self.context
        app = context.app
        app.includes = Globs(app.default_includes)
        app.excludes = Globs(app.default_excludes)
        app.cwd = cwd
        self._new_paths = []

    def handle_before_script(self, cwd: Path):
        context = self.context
        app = context.app
        app.script = (cwd / ".kubernator.py")

    def handle_after_script(self, cwd: Path):
        context = self.context
        app = context.app
        del app.script

    def handle_after_dir(self, cwd: Path):
        context = self.context
        app = context.app

        for f in scan_dir(logger, cwd, lambda d: d.is_dir(), app.excludes, app.includes):
            self._new_paths.append((PropertyDict(_parent=context), f))

        self.path_q.extend(reversed(self._new_paths))

        del app.cwd

    def repository(self, repo):
        repository = Repository(repo, self._repo_cred_augmentation)
        if repository in self.repos:
            repository = self.repos[repository]
        else:
            self.repos[repository] = repository
            repository.init(logger, self.context)
            self.register_cleanup(repository)

        return repository

    def walk_local(self, *paths: Union[Path, str, bytes], keep_context=False):
        for path in paths:
            p = Path(path)
            if not p.is_absolute():
                p = self.context.app.cwd / p
            self._add_local(p, keep_context)

    def walk_remote(self, repo, *path_prefixes: Union[Path, str, bytes], keep_context=False):
        repository = self.repository(repo)

        if path_prefixes:
            for path_prefix in path_prefixes:
                path = Path(path_prefix)
                if path.is_absolute():
                    path = Path(*path.parts[1:])
                self._add_local(repository.local_dir / path, keep_context)
        else:
            self._add_local(repository.local_dir, keep_context)

    def set_context(self, context):
        # We are managing the context for everyone so we don't actually set it anywhere
        pass

    def _add_local(self, path: Path, keep_context=False):
        logger.info("Adding %s to the plan%s", self._display_path(path),
                    " (in parent context)" if keep_context else "")
        self._new_paths.append((self.context if keep_context else PropertyDict(_parent=self.context), path))

    def _repository_credentials_provider(self,
                                         provider: Optional[
                                             Callable[[urllib.parse.SplitResult], tuple[
                                                 Optional[str], Optional[str], Optional[str]]]]):
        self.context.app._repository_credentials_provider = provider

    def _repo_cred_augmentation(self, url):
        rcp = self.context.app._repository_credentials_provider
        if not rcp:
            return url

        scheme, username, password = rcp(url)
        return urllib.parse.SplitResult(scheme if scheme else url.scheme,
                                        ((
                                             username +
                                             (
                                                 ":" + password if password else "") + "@"
                                             if username else "") + url.hostname)
                                        if username or password
                                        else url.netloc,
                                        url.path, url.query, url.fragment)

    def _path_to_repository(self, path: Path) -> Repository:
        for r in self.repos.values():
            if path.is_relative_to(r.local_dir):
                return r

    def _display_path(self, path: Path) -> str:
        repo = self._path_to_repository(path)
        return "<%s> %s" % (repo.url_str, path) if repo else str(path)

    def _run(self, *args, **kwargs):
        return run(*args, **kwargs)

    def _run_capturing_out(self, *args, **kwargs):
        return run_capturing_out(*args, **kwargs)

    def __repr__(self):
        return "Kubernator"


def main():
    args = define_arg_parse().parse_args()
    init_logging(args.verbose, args.log_format, args.log_file)

    try:
        with App(args) as app:
            app.run()
    except SystemExit as e:
        return e.code
    except Exception as e:
        logger.fatal("Kubernator terminated with an error: %s", e, exc_info=e)
        return 1
    else:
        logger.info("Kubernator terminated successfully")
    finally:
        logging.shutdown()
