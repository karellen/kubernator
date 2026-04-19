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
"""K8s CEL extension library: CIDR parsing.

Mirrors ``k8s.io/apiserver/pkg/cel/library/cidr.go``.
"""

from __future__ import annotations

import ipaddress

import celpy.celtypes as ct


def _parse_network(value):
    if isinstance(value, ct.MapType) and "_cidr" in value:
        return ipaddress.ip_network(str(value["cidr"]), strict=False)
    return ipaddress.ip_network(str(value), strict=False)


def _parse_address(value):
    if isinstance(value, ct.MapType) and "_ip" in value:
        return ipaddress.ip_address(str(value["address"]))
    return ipaddress.ip_address(str(value))


def cidr(value):
    """``cidr("10.0.0.0/8")`` → CIDR object."""
    net = _parse_network(value)
    return ct.MapType({
        "_cidr": True,
        "cidr": ct.StringType(str(net)),
        "family": ct.IntType(net.version),
        "prefixLength": ct.IntType(net.prefixlen),
    })


def isCIDR(value):  # noqa: N802 — CEL identifier
    """``isCIDR("10.0.0.0/8")`` → bool."""
    try:
        _parse_network(value)
        return ct.BoolType(True)
    except (ValueError, TypeError):
        return ct.BoolType(False)


def containsIP(net_value, ip_value):  # noqa: N802 — CEL identifier
    """``cidr.containsIP(ip)`` → bool."""
    return ct.BoolType(_parse_address(ip_value) in _parse_network(net_value))


def containsCIDR(outer, inner):  # noqa: N802 — CEL identifier
    return ct.BoolType(_parse_network(outer).supernet_of(_parse_network(inner)))


def prefixLength(value):  # noqa: N802 — CEL identifier
    return ct.IntType(_parse_network(value).prefixlen)


def masked(value):
    net = _parse_network(value)
    # Return canonical (network address) string form.
    return ct.MapType({
        "_cidr": True,
        "cidr": ct.StringType(str(net)),
        "family": ct.IntType(net.version),
        "prefixLength": ct.IntType(net.prefixlen),
    })


__all__ = [
    "cidr",
    "isCIDR",
    "containsIP",
    "containsCIDR",
    "prefixLength",
    "masked",
]
