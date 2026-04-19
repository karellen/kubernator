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
"""K8s CEL extension library: regex.

Mirrors ``k8s.io/apiserver/pkg/cel/library/regex.go`` — provides
``find`` and ``findAll`` as string member methods.

K8s uses google-re2 (RE2) for regex; the Python port relies on the
``re`` stdlib module. The two engines disagree on a small number of
edge cases (named-group syntax, possessive quantifiers, lookarounds);
patterns produced by Kubernetes contributors typically stay within the
RE2 subset, so this is rarely an issue in practice.
"""

from __future__ import annotations

import re

import celpy.celtypes as ct


def find(s, pattern):
    """``str.find(pattern)`` — first match or empty string if no match."""
    m = re.search(str(pattern), str(s))
    return ct.StringType(m.group(0)) if m else ct.StringType("")


def findAll(s, pattern, *limit):  # noqa: N802 — CEL identifier
    """``str.findAll(pattern[, limit])`` — list of matches; optional limit."""
    matches = re.findall(str(pattern), str(s))
    if limit:
        matches = matches[: int(limit[0])]
    # findall returns tuples for grouped patterns — flatten to plain strings.
    out = ct.ListType()
    for m in matches:
        if isinstance(m, tuple):
            out.append(ct.StringType(m[0] if m else ""))
        else:
            out.append(ct.StringType(m))
    return out


__all__ = ["find", "findAll"]
