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
"""K8s CEL extension library: named string formats.

Mirrors ``k8s.io/apiserver/pkg/cel/library/format.go``. Exposes a
``format.named("<name>")`` that returns a "matcher" object with a
``validate(value) -> list[string]`` method (empty list means valid).

celpy doesn't support a real ``format`` namespace, so we expose the
matcher via the global function ``namedFormat("<name>")`` (which can
also be called as ``"name".namedFormat()`` per CEL method-call sugar).
The shape mirrors the K8s API; the regexes are ported verbatim from
the Go originals listed below.
"""

from __future__ import annotations

import re
from typing import Callable, Mapping

import celpy.celtypes as ct

# ---------------------------------------------------------------------------
# Named format regexes (ported from k8s.io/apimachinery/pkg/util/validation).
# ---------------------------------------------------------------------------

DNS1123_LABEL_FMT = r"[a-z0-9]([-a-z0-9]*[a-z0-9])?"
DNS1123_LABEL_MAX = 63
DNS1123_LABEL_RE = re.compile(rf"^{DNS1123_LABEL_FMT}$")

DNS1123_SUBDOMAIN_FMT = rf"{DNS1123_LABEL_FMT}(\.{DNS1123_LABEL_FMT})*"
DNS1123_SUBDOMAIN_MAX = 253
DNS1123_SUBDOMAIN_RE = re.compile(rf"^{DNS1123_SUBDOMAIN_FMT}$")

DNS1035_LABEL_FMT = r"[a-z]([-a-z0-9]*[a-z0-9])?"
DNS1035_LABEL_MAX = 63
DNS1035_LABEL_RE = re.compile(rf"^{DNS1035_LABEL_FMT}$")

QNAME_CHAR_FMT = r"[A-Za-z0-9]"
QNAME_EXT_CHAR_FMT = r"[-A-Za-z0-9_.]"
QUALIFIED_NAME_FMT = (
    rf"({QNAME_CHAR_FMT}{QNAME_EXT_CHAR_FMT}*)?{QNAME_CHAR_FMT}"
)
QUALIFIED_NAME_MAX = 63
QUALIFIED_NAME_RE = re.compile(rf"^{QUALIFIED_NAME_FMT}$")

LABEL_VALUE_FMT = (
    rf"(({QNAME_CHAR_FMT}{QNAME_EXT_CHAR_FMT}*)?{QNAME_CHAR_FMT})?"
)
LABEL_VALUE_MAX = 63
LABEL_VALUE_RE = re.compile(rf"^{LABEL_VALUE_FMT}$")

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Liberal subset; full RFC3986 URI is delegated to ``urllib.parse.urlsplit``.
URI_FORBIDDEN = re.compile(r"[\s<>\"]")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?"
    r"([Zz]|[+\-]\d{2}:\d{2})$"
)


def _check_dns1123_label(value: str) -> list[str]:
    errs: list[str] = []
    if len(value) > DNS1123_LABEL_MAX:
        errs.append(f"must be no more than {DNS1123_LABEL_MAX} characters")
    if not DNS1123_LABEL_RE.match(value):
        errs.append("a lowercase RFC 1123 label must consist of lower case "
                    "alphanumeric characters or '-', and must start and end "
                    "with an alphanumeric character")
    return errs


def _check_dns1123_subdomain(value: str) -> list[str]:
    errs: list[str] = []
    if len(value) > DNS1123_SUBDOMAIN_MAX:
        errs.append(f"must be no more than {DNS1123_SUBDOMAIN_MAX} characters")
    if not DNS1123_SUBDOMAIN_RE.match(value):
        errs.append("a lowercase RFC 1123 subdomain must consist of lower "
                    "case alphanumeric characters, '-' or '.', and must "
                    "start and end with an alphanumeric character")
    return errs


def _check_dns1035_label(value: str) -> list[str]:
    errs: list[str] = []
    if len(value) > DNS1035_LABEL_MAX:
        errs.append(f"must be no more than {DNS1035_LABEL_MAX} characters")
    if not DNS1035_LABEL_RE.match(value):
        errs.append("a DNS-1035 label must consist of lower case alphanumeric "
                    "characters or '-', start with an alphabetic character, "
                    "and end with an alphanumeric character")
    return errs


def _check_qualified_name(value: str) -> list[str]:
    errs: list[str] = []
    parts = value.split("/")
    if len(parts) == 1:
        name = parts[0]
    elif len(parts) == 2:
        prefix, name = parts
        if not prefix:
            errs.append("prefix part must be non-empty")
        else:
            errs.extend("prefix part: " + e for e in _check_dns1123_subdomain(prefix))
    else:
        errs.append("a qualified name must consist of alphanumeric characters,"
                    " '-', '_' or '.', with an optional DNS subdomain prefix and"
                    " '/'")
        return errs
    if not name:
        errs.append("name part must be non-empty")
    elif len(name) > QUALIFIED_NAME_MAX:
        errs.append(f"name part must be no more than {QUALIFIED_NAME_MAX} characters")
    elif not QUALIFIED_NAME_RE.match(name):
        errs.append("name part must consist of alphanumeric characters, '-', "
                    "'_' or '.', and must start and end with an alphanumeric"
                    " character")
    return errs


def _check_label_value(value: str) -> list[str]:
    errs: list[str] = []
    if len(value) > LABEL_VALUE_MAX:
        errs.append(f"must be no more than {LABEL_VALUE_MAX} characters")
    if not LABEL_VALUE_RE.match(value):
        errs.append("a valid label must be an empty string or consist of "
                    "alphanumeric characters, '-', '_' or '.', and must start"
                    " and end with an alphanumeric character")
    return errs


def _check_uri(value: str) -> list[str]:
    if URI_FORBIDDEN.search(value):
        return ["must not contain whitespace or unsafe characters"]
    import urllib.parse
    parsed = urllib.parse.urlsplit(value)
    if not parsed.scheme:
        return ["must be a valid URI (no scheme detected)"]
    return []


def _check_uuid(value: str) -> list[str]:
    return [] if UUID_RE.match(value) else ["must be a valid UUID"]


def _check_byte(value: str) -> list[str]:
    import base64
    try:
        base64.b64decode(value, validate=True)
        return []
    except (ValueError, TypeError):
        return ["must be valid base64-encoded data"]


def _check_date(value: str) -> list[str]:
    if not DATE_RE.match(value):
        return ["must be in YYYY-MM-DD format"]
    import datetime
    try:
        datetime.date.fromisoformat(value)
        return []
    except ValueError as e:
        return [str(e)]


def _check_datetime(value: str) -> list[str]:
    if not DATETIME_RE.match(value):
        return ["must be a valid RFC3339 datetime"]
    import datetime
    try:
        # Python tolerates 'Z' since 3.11; accept lowercase too.
        datetime.datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
        return []
    except ValueError as e:
        return [str(e)]


_CHECKERS: Mapping[str, Callable[[str], list]] = {
    "dns1123Label": _check_dns1123_label,
    "dns1123Subdomain": _check_dns1123_subdomain,
    "dns1035Label": _check_dns1035_label,
    "qualifiedName": _check_qualified_name,
    "labelValue": _check_label_value,
    "uri": _check_uri,
    "uuid": _check_uuid,
    "byte": _check_byte,
    "date": _check_date,
    "datetime": _check_datetime,
}


def named(name):
    """``format.named("<n>")`` → matcher.

    The returned matcher is a CEL ``MapType`` carrying a callable
    ``validate`` reference. We expose validation through the
    ``validateFormat(matcher, value)`` global function below since
    celpy does not support attaching arbitrary methods to MapType.
    """
    if str(name) not in _CHECKERS:
        raise ValueError(f"unknown named format: {name!r}")
    return ct.MapType({"name": ct.StringType(str(name))})


def validateFormat(matcher, value):  # noqa: N802 — CEL identifier
    """``matcher.validate(value)`` (or ``validateFormat(matcher, value)``)
    returns a list of error strings; empty list means the value is
    valid for that format."""
    name = str(matcher["name"])
    checker = _CHECKERS[name]
    errs = checker(str(value))
    return ct.ListType([ct.StringType(e) for e in errs])


def namedFormat(name):  # noqa: N802 — CEL identifier
    """Alias for :func:`named` callable as a member method of strings:
    ``"dns1123Label".namedFormat()``."""
    return named(name)


__all__ = ["named", "namedFormat", "validateFormat"]
