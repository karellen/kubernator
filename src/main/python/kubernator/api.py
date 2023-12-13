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

import fnmatch
import json
import logging
import os
import platform
import re
import sys
import traceback
import urllib.parse
from collections.abc import Callable
from collections.abc import Iterable, MutableSet, Reversible
from enum import Enum
from hashlib import sha256
from io import StringIO as io_StringIO
from pathlib import Path
from shutil import rmtree
from subprocess import CalledProcessError
from types import GeneratorType
from typing import Optional, Union, MutableSequence

import requests
import yaml
from appdirs import user_config_dir
from jinja2 import (Environment,
                    ChainableUndefined,
                    make_logging_undefined,
                    Template as JinjaTemplate,
                    pass_context)
from jsonschema import validators

_CACHE_HEADER_TRANSLATION = {"etag": "if-none-match",
                             "last-modified": "if-modified-since"}
_CACHE_HEADERS = ("etag", "last-modified")


def calling_frame_source(depth=2):
    f = traceback.extract_stack(limit=depth + 1)[0]
    return f"file {f.filename}, line {f.lineno} in {f.name}"


def re_filter(name: str, patterns: Iterable[re.Pattern]):
    for pattern in patterns:
        if pattern.match(name):
            return True


def to_patterns(*patterns):
    return [re.compile(fnmatch.translate(p)) for p in patterns]


def scan_dir(logger, path: Path, path_filter: Callable[[os.DirEntry], bool], excludes, includes):
    logger.debug("Scanning %s, excluding %s, including %s", path, excludes, includes)
    with os.scandir(path) as it:  # type: Iterable[os.DirEntry]
        files = {f: f for f in
                 sorted(d.name for d in it if path_filter(d) and not re_filter(d.name, excludes))}

    for include in includes:
        logger.trace("Considering include %s in %s", include, path)
        for f in list(files.keys()):
            if include.match(f):
                del files[f]
                logger.debug("Selecting %s in %s as it matches %s", f, path, include)
                yield path / f


class FileType(Enum):
    JSON = (json.load,)
    YAML = (yaml.safe_load_all,)

    def __init__(self, func):
        self.func = func


def _load_file(logger, path: Path, file_type: FileType, source=None) -> Iterable[dict]:
    with open(path, "rb") as f:
        try:
            data = file_type.func(f)
            if isinstance(data, GeneratorType):
                data = list(data)
            return data
        except Exception as e:
            logger.error("Failed parsing %s using %s", source or path, file_type, exc_info=e)
            raise


def _download_remote_file(url, file_name, cache: dict):
    with requests.get(url, headers=cache, stream=True) as r:
        r.raise_for_status()
        if r.status_code != 304:
            with open(file_name, "wb") as out:
                for chunk in r.iter_content(chunk_size=65535):
                    out.write(chunk)
            return dict(r.headers)


def get_cache_dir(category: str, sub_category: str = None):
    config_dir = Path(user_config_dir("kubernator")) / category
    if sub_category:
        config_dir = config_dir / sub_category
    if not config_dir.exists():
        config_dir.mkdir(parents=True)

    return config_dir


def download_remote_file(logger, url: str, category: str = "k8s", sub_category: str = None,
                         downloader=_download_remote_file):
    config_dir = get_cache_dir(category, sub_category)

    file_name = config_dir / sha256(url.encode("UTF-8")).hexdigest()
    cache_file_name = file_name.with_suffix(".cache")
    logger.trace("Cache file for %s is %s.cache", url, file_name)

    cache = {}
    if cache_file_name.exists():
        logger.trace("Loading cache file from %s", cache_file_name)
        try:
            with open(cache_file_name, "rb") as cache_f:
                cache = json.load(cache_f)
        except (IOError, ValueError) as e:
            logger.trace("Failed loading cache file from %s (cleaning up)", cache_file_name, exc_info=e)
            cache_file_name.unlink(missing_ok=True)

    logger.trace("Downloading %s into %s%s", url, file_name, " (caching)" if cache else "")
    headers = downloader(url, file_name, cache)
    up_to_date = False
    if not headers:
        logger.trace("File %s(%s) is up-to-date", url, file_name.name)
        up_to_date = True
    else:
        cache = {_CACHE_HEADER_TRANSLATION.get(k.lower(), k): v
                 for k, v in headers.items()
                 if k.lower() in _CACHE_HEADERS}

        logger.trace("Update cache file in %s: %r", cache_file_name, cache)
        with open(cache_file_name, "wt") as cache_f:
            json.dump(cache, cache_f)

    return file_name, up_to_date


def load_remote_file(logger, url, file_type: FileType, category: str = "k8s", sub_category: str = None,
                     downloader=_download_remote_file):
    file_name, _ = download_remote_file(logger, url, category, sub_category, downloader=downloader)
    logger.debug("Loading %s from %s using %s", url, file_name, file_type.name)
    return _load_file(logger, file_name, file_type, url)


def load_file(logger, path: Path, file_type: FileType, source=None) -> Iterable[dict]:
    logger.debug("Loading %s using %s", source or path, file_type.name)
    return _load_file(logger, path, file_type)


def validator_with_defaults(validator_class):
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator, properties, instance, schema):
        for property, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(property, subschema["default"])

        for error in validate_properties(validator, properties, instance, schema):
            yield error

    return validators.extend(validator_class, {"properties": set_defaults})


class _PropertyList(MutableSequence):

    def __init__(self, seq, read_parent, name):
        self.__read_seq = seq
        self.__read_parent = read_parent
        self.__write_parent = None
        self.__write_seq = None
        self.__name = name

    def __iter__(self):
        return self.__read_seq.__iter__()

    def __mul__(self, __n):
        return self.__read_seq.__mul__(__n)

    def __rmul__(self, __n):
        return self.__read_seq.__rmul__(__n)

    def __imul__(self, __n):
        return self.__read_seq.__imul__(__n)

    def __contains__(self, __o):
        return self.__read_seq.__contains__(__o)

    def __reversed__(self):
        return self.__read_seq.__reversed__()

    def __gt__(self, __x):
        return self.__read_seq.__gt__(__x)

    def __ge__(self, __x):
        return self.__read_seq.__ge__(__x)

    def __lt__(self, __x):
        return self.__read_seq.__lt__(__x)

    def __le__(self, __x):
        return self.__read_seq.__le__(__x)

    def __len__(self):
        return self.__read_seq.__len__()

    def count(self, __value):
        return self.__read_seq.count(__value)

    def copy(self):
        while True:
            try:
                return self.__write_seq.copy()
            except AttributeError:
                self.__clone()

    def __getitem__(self, __i):
        return self.__read_seq.__getitem__(__i)

    def append(self, __object):
        while True:
            try:
                return self.__write_seq.append(__object)
            except AttributeError:
                self.__clone()

    def extend(self, __iterable):
        while True:
            try:
                return self.__write_seq.extend(__iterable)
            except AttributeError:
                self.__clone()

    def pop(self, __index=None):
        while True:
            try:
                return self.__write_seq.pop(__index)
            except AttributeError:
                self.__clone()

    def insert(self, __index, __object):
        while True:
            try:
                return self.__write_seq.insert(__index, __object)
            except AttributeError:
                self.__clone()

    def remove(self, __value):
        while True:
            try:
                return self.__write_seq.remove(__value)
            except AttributeError:
                self.__clone()

    def sort(self, *, key=None, reverse=False):
        while True:
            try:
                return self.__write_seq.sort(key=key, reverse=reverse)
            except AttributeError:
                self.__clone()

    def __setitem__(self, __i, __o):
        while True:
            try:
                return self.__write_seq.__setitem__(__i, __o)
            except AttributeError:
                self.__clone()

    def __delitem__(self, __i):
        while True:
            try:
                return self.__write_seq.__delitem__(__i)
            except AttributeError:
                self.__clone()

    def __add__(self, __x):
        while True:
            try:
                return self.__write_seq.__add__(__x)
            except AttributeError:
                self.__clone()

    def __iadd__(self, __x):
        while True:
            try:
                return self.__write_seq.__iadd__(__x)
            except AttributeError:
                self.__clone()

    def clear(self):
        while True:
            try:
                return self.__write_seq.clear()
            except AttributeError:
                self.__clone()

    def reverse(self):
        while True:
            try:
                return self.__write_seq.reverse()
            except AttributeError:
                self.__clone()

    def __clone(self):
        if self.__read_parent == self.__write_parent:
            self.__write_seq = self.__read_seq
        else:
            self.__write_seq = self.__read_seq.copy()
            self.__read_seq = self.__write_seq

            setattr(self.__write_parent, self.__name, self.__write_seq)


class PropertyDict:
    def __init__(self, _dict=None, _parent=None):
        self.__dict__["_PropertyDict__dict"] = _dict or {}
        self.__dict__["_PropertyDict__parent"] = _parent

    def __getattr__(self, item):
        v = self.__getattr(item)
        if isinstance(v, _PropertyList):
            v._PropertyList__write_parent = self
        return v

    def __getattr(self, item):
        try:
            v = self.__dict[item]
            if isinstance(v, list):
                v = _PropertyList(v, self, item)
            return v
        except KeyError:
            parent = self.__parent
            if parent is not None:
                return parent.__getattr(item)
            raise AttributeError("no attribute %r" % item) from None

    def __setattr__(self, key, value):
        if key.startswith("_PropertyDict__"):
            raise AttributeError("prohibited attribute %r" % key)
        if isinstance(value, dict):
            parent_dict = None
            if self.__parent is not None:
                try:
                    parent_dict = self.__parent.__getattr__(key)
                    if not isinstance(parent_dict, PropertyDict):
                        raise ValueError("cannot override a scalar with a synthetic object for attribute %s", key)
                except AttributeError:
                    pass
            value = PropertyDict(value, _parent=parent_dict)
        self.__dict[key] = value

    def __delattr__(self, item):
        del self.__dict[item]

    def __len__(self):
        return len(self.__dir__())

    def __getitem__(self, item):
        return self.__dict.__getitem__(item)

    def __setitem__(self, key, value):
        self.__dict.__setitem__(key, value)

    def __delitem__(self, key):
        self.__dict.__delitem__(key)

    def __contains__(self, item):
        try:
            self.__dict[item]
            return True
        except KeyError:
            parent = self.__parent
            if parent is not None:
                return parent.__contains__(item)
            return False

    def __dir__(self) -> Iterable[str]:
        result: set[str] = set()
        result.update(self.__dict.keys())
        if self.__parent is not None:
            result.update(self.__parent.__dir__())
        return result

    def __repr__(self):
        return "PropertyDict[%r]" % self.__dict


def config_parent(config: PropertyDict):
    return config._PropertyDict__parent


def config_as_dict(config: PropertyDict):
    return {k: config[k] for k in dir(config)}


def config_get(config: PropertyDict, key: str, default=None):
    try:
        return config[key]
    except KeyError:
        return default


class Globs(MutableSet[Union[str, re.Pattern]]):
    def __init__(self, source: Optional[list[Union[str, re.Pattern]]] = None,
                 immutable=False):
        self._immutable = immutable
        if source:
            self._list = [self.__wrap__(v) for v in source]
        else:
            self._list = []

    def __wrap__(self, item: Union[str, re.Pattern]):
        if isinstance(item, re.Pattern):
            return item
        return re.compile(fnmatch.translate(item))

    def __contains__(self, item: Union[str, re.Pattern]):
        return self._list.__contains__(self.__wrap__(item))

    def __iter__(self):
        return self._list.__iter__()

    def __len__(self):
        return self._list.__len__()

    def add(self, value: Union[str, re.Pattern]):
        if self._immutable:
            raise RuntimeError("immutable")

        _list = self._list
        value = self.__wrap__(value)
        if value not in _list:
            _list.append(value)

    def extend(self, values: Iterable[Union[str, re.Pattern]]):
        for v in values:
            self.add(v)

    def discard(self, value: Union[str, re.Pattern]):
        if self._immutable:
            raise RuntimeError("immutable")

        _list = self._list
        value = self.__wrap__(value)
        if value in _list:
            _list.remove(value)

    def add_first(self, value: Union[str, re.Pattern]):
        if self._immutable:
            raise RuntimeError("immutable")

        _list = self._list
        value = self.__wrap__(value)
        if value not in _list:
            _list.insert(0, value)

    def extend_first(self, values: Reversible[Union[str, re.Pattern]]):
        for v in reversed(values):
            self.add_first(v)

    def __str__(self):
        return self._list.__str__()

    def __repr__(self):
        return f"Globs[{self._list}]"


class TemplateEngine:
    VARIABLE_START_STRING = "{${"
    VARIABLE_END_STRING = "}$}"

    def __init__(self, logger):
        self.template_failures = 0
        self.templates = {}

        class CollectingUndefined(ChainableUndefined):
            __slots__ = ()

            def __str__(self):
                self.template_failures += 1
                return super().__str__()

        logging_undefined = make_logging_undefined(
            logger=logger,
            base=CollectingUndefined
        )

        @pass_context
        def variable_finalizer(ctx, value):
            normalized_value = str(value)
            if self.VARIABLE_START_STRING in normalized_value and self.VARIABLE_END_STRING in normalized_value:
                value_template_content = sys.intern(normalized_value)
                env: Environment = ctx.environment
                value_template = self.templates.get(value_template_content)
                if not value_template:
                    value_template = env.from_string(value_template_content, env.globals)
                    self.templates[value_template_content] = value_template
                return value_template.render(ctx.parent)

            return normalized_value

        self.env = Environment(variable_start_string=self.VARIABLE_START_STRING,
                               variable_end_string=self.VARIABLE_END_STRING,
                               autoescape=False,
                               finalize=variable_finalizer,
                               undefined=logging_undefined)

    def from_string(self, template):
        return self.env.from_string(template)

    def failures(self):
        return self.template_failures


class Template:
    def __init__(self, name: str, template: JinjaTemplate, defaults: dict = None, path=None, source=None):
        self.name = name
        self.source = source
        self.path = path
        self.template = template
        self.defaults = defaults

    def render(self, context: dict, values: dict):
        variables = {"ktor": context,
                     "values": (self.defaults or {}) | values}
        return self.template.render(variables)


class StringIO:
    def __init__(self, trimmed=True):
        self.write = self.write_trimmed if trimmed else self.write_untrimmed
        self._buf = io_StringIO()

    def write_untrimmed(self, line):
        self._buf.write(line)

    def write_trimmed(self, line):
        self._buf.write(f"{line}\n")

    def getvalue(self):
        return self._buf.getvalue()


class StripNL:
    def __init__(self, func):
        self._func = func

    def __call__(self, line: str):
        return self._func(line.rstrip("\r\n"))


def log_level_to_verbosity_count(level: int):
    return int(-level / 10 + 6)


def clone_url_str(url):
    return urllib.parse.urlunsplit(url[:3] + ("", ""))  # no query or fragment


def prepend_os_path(path):
    paths = os.environ["PATH"].split(os.pathsep)
    if path not in paths:
        paths.insert(0, path)
        os.environ["PATH"] = os.pathsep.join(paths)
        return True
    return False


_GOLANG_MACHINE = platform.machine().lower()
if _GOLANG_MACHINE == "x86_64":
    _GOLANG_MACHINE = "amd64"

_GOLANG_OS = platform.system().lower()


def get_golang_machine():
    return _GOLANG_MACHINE


def get_golang_os():
    return _GOLANG_OS


def sha256_file_digest(path):
    h = sha256()
    with open(path, "rb") as f:
        h.update(f.read(65535))
    return h.hexdigest()


class Repository:
    logger = logging.getLogger("kubernator.repository")
    git_logger = logger.getChild("git")

    def __init__(self, repo, cred_aug=None):
        url = urllib.parse.urlsplit(repo)
        self.url = url
        self.url_str = urllib.parse.urlunsplit(url[:4] + ("",))
        self._cred_aug = cred_aug
        self._hash_obj = (url.hostname if url.username or url.password else url.netloc,
                          url.path,
                          url.query)

        self.clone_url = None  # Actual URL components used in cloning operations
        self.clone_url_str = None  # Actual URL string used in cloning operations
        self.ref = None
        self.local_dir = None

    def __eq__(self, o: object) -> bool:
        if isinstance(o, Repository):
            return self._hash_obj == o._hash_obj

    def __hash__(self) -> int:
        return hash(self._hash_obj)

    def init(self, logger, context):
        run = context.app.run
        run_capturing_out = context.app.run_capturing_out

        url = self.url
        if self._cred_aug:
            url = self._cred_aug(url)

        self.clone_url = url
        self.clone_url_str = clone_url_str(url)

        query = urllib.parse.parse_qs(self.url.query)
        ref = query.get("ref")
        if ref:
            self.ref = ref[0]

        config_dir = get_cache_dir("git")

        git_cache = config_dir / sha256(self.clone_url_str.encode("UTF-8")).hexdigest()

        if git_cache.exists() and git_cache.is_dir() and (git_cache / ".git").exists():
            try:
                proc = run(["git", "status"], None, None, cwd=git_cache)
                proc.wait()
            except CalledProcessError:
                rmtree(git_cache)

        self.local_dir = str(git_cache)

        stdout_logger = StripNL(self.git_logger.debug)
        stderr_logger = StripNL(self.git_logger.info)
        if git_cache.exists():
            if not self.ref:
                ref = run_capturing_out(["git", "symbolic-ref", "refs/remotes/origin/HEAD", "--short"],
                                        stderr_logger, cwd=git_cache)
            else:
                ref = self.ref
            run(["git", "checkout", ref], stdout_logger, stderr_logger, cwd=git_cache).wait()
            run(["git", "clean", "-f"], stdout_logger, stderr_logger, cwd=git_cache).wait()
            run(["git", "reset", "--hard", ref], stdout_logger, stderr_logger, cwd=git_cache).wait()
            run(["git", "pull"], stdout_logger, stderr_logger, cwd=git_cache).wait()
        else:
            self.logger.info("Initializing %s -> %s", self.url_str, self.local_dir)
            args = (["git", "clone", "--depth", "1",
                     "-" + ("v" * log_level_to_verbosity_count(logger.getEffectiveLevel()))] +
                    (["-b", self.ref] if self.ref else []) +
                    ["--", self.clone_url_str, self.local_dir])
            safe_args = [c if c != self.clone_url_str else self.url_str for c in args]
            proc = run(args, stdout_logger, stderr_logger, safe_args=safe_args)
            proc.wait()

    def cleanup(self):
        if False and self.local_dir:
            self.logger.info("Cleaning up %s -> %s", self.url_str, self.local_dir)
            rmtree(self.local_dir)


class KubernatorPlugin:
    _name = None

    def set_context(self, context):
        raise NotImplementedError

    def register(self, **kwargs):
        pass

    def handle_init(self):
        pass

    def handle_start(self):
        pass

    def handle_before_dir(self, cwd: Path):
        pass

    def handle_before_script(self, cwd: Path):
        pass

    def handle_after_script(self, cwd: Path):
        pass

    def handle_after_dir(self, cwd: Path):
        pass

    def handle_apply(self):
        pass

    def handle_verify(self):
        pass

    def handle_shutdown(self):
        pass
