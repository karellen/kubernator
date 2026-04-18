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
"""K8s CEL extension library: IP address parsing.

Mirrors ``k8s.io/apiserver/pkg/cel/library/ip.go``.
"""

from __future__ import annotations

import ipaddress

import celpy.celtypes as ct


def _parse(value):
    if isinstance(value, ct.MapType) and "_ip" in value:
        return ipaddress.ip_address(str(value["address"]))
    return ipaddress.ip_address(str(value))


def ip(value):
    """``ip("10.0.0.1")`` → IP address object."""
    addr = _parse(value)
    return ct.MapType({
        "_ip": True,
        "address": ct.StringType(str(addr)),
        "family": ct.IntType(addr.version),
    })


def isIP(value):  # noqa: N802 — CEL identifier
    """``isIP("10.0.0.1")`` → bool. Also callable as a string method."""
    try:
        _parse(value)
        return ct.BoolType(True)
    except (ValueError, TypeError):
        return ct.BoolType(False)


def family(value):
    """``ip.family`` shorthand — IP version (4 or 6)."""
    return ct.IntType(_parse(value).version)


def isLoopback(value):  # noqa: N802 — CEL identifier
    return ct.BoolType(_parse(value).is_loopback)


def isUnspecified(value):  # noqa: N802 — CEL identifier
    return ct.BoolType(_parse(value).is_unspecified)


def isLinkLocalUnicast(value):  # noqa: N802 — CEL identifier
    return ct.BoolType(_parse(value).is_link_local)


def isLinkLocalMulticast(value):  # noqa: N802 — CEL identifier
    addr = _parse(value)
    return ct.BoolType(addr.is_multicast and addr.is_link_local)


def isGlobalUnicast(value):  # noqa: N802 — CEL identifier
    addr = _parse(value)
    return ct.BoolType(addr.is_global and not addr.is_multicast)


__all__ = [
    "ip",
    "isIP",
    "family",
    "isLoopback",
    "isUnspecified",
    "isLinkLocalUnicast",
    "isLinkLocalMulticast",
    "isGlobalUnicast",
]
