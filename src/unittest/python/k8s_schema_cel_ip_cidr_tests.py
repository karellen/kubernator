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

from gevent.monkey import patch_all, is_anything_patched

if not is_anything_patched():
    patch_all()

import unittest

import celpy.celtypes as ct

from kubernator.plugins.k8s_schema.cel.extensions.ip_lib import (
    family,
    ip,
    isGlobalUnicast,
    isIP,
    isLinkLocalMulticast,
    isLinkLocalUnicast,
    isLoopback,
    isUnspecified,
)
from kubernator.plugins.k8s_schema.cel.extensions.cidr_lib import (
    cidr,
    containsCIDR,
    containsIP,
    isCIDR,
    masked,
    prefixLength,
)


# ---- IP ----

class IPTest(unittest.TestCase):
    def test_ipv4(self):
        result = ip(ct.StringType("10.0.0.1"))
        self.assertEqual(str(result["address"]), "10.0.0.1")
        self.assertEqual(result["family"], ct.IntType(4))

    def test_ipv6(self):
        result = ip(ct.StringType("::1"))
        self.assertIn("_ip", result)
        self.assertEqual(result["family"], ct.IntType(6))

    def test_passthrough_already_wrapped(self):
        wrapped = ip(ct.StringType("10.0.0.1"))
        result = ip(wrapped)
        self.assertEqual(str(result["address"]), "10.0.0.1")


class IsIPTest(unittest.TestCase):
    def test_valid_ipv4(self):
        self.assertEqual(isIP(ct.StringType("192.168.1.1")), ct.BoolType(True))

    def test_valid_ipv6(self):
        self.assertEqual(isIP(ct.StringType("::1")), ct.BoolType(True))

    def test_invalid(self):
        self.assertEqual(isIP(ct.StringType("nope")), ct.BoolType(False))


class FamilyTest(unittest.TestCase):
    def test_ipv4(self):
        self.assertEqual(family(ct.StringType("10.0.0.1")), ct.IntType(4))

    def test_ipv6(self):
        self.assertEqual(family(ct.StringType("::1")), ct.IntType(6))


class IPPropertiesTest(unittest.TestCase):
    def test_isLoopback_v4(self):
        self.assertEqual(isLoopback(ct.StringType("127.0.0.1")),
                         ct.BoolType(True))

    def test_isLoopback_v6(self):
        self.assertEqual(isLoopback(ct.StringType("::1")),
                         ct.BoolType(True))

    def test_isLoopback_false(self):
        self.assertEqual(isLoopback(ct.StringType("10.0.0.1")),
                         ct.BoolType(False))

    def test_isUnspecified(self):
        self.assertEqual(isUnspecified(ct.StringType("0.0.0.0")),
                         ct.BoolType(True))
        self.assertEqual(isUnspecified(ct.StringType("10.0.0.1")),
                         ct.BoolType(False))

    def test_isLinkLocalUnicast(self):
        self.assertEqual(isLinkLocalUnicast(ct.StringType("169.254.1.1")),
                         ct.BoolType(True))
        self.assertEqual(isLinkLocalUnicast(ct.StringType("10.0.0.1")),
                         ct.BoolType(False))

    def test_isLinkLocalMulticast(self):
        # Python's ipaddress.is_link_local covers unicast fe80::/10 only,
        # so no multicast address satisfies both is_multicast AND is_link_local.
        self.assertEqual(isLinkLocalMulticast(ct.StringType("ff02::1")),
                         ct.BoolType(False))
        self.assertEqual(isLinkLocalMulticast(ct.StringType("10.0.0.1")),
                         ct.BoolType(False))

    def test_isGlobalUnicast(self):
        self.assertEqual(isGlobalUnicast(ct.StringType("8.8.8.8")),
                         ct.BoolType(True))
        self.assertEqual(isGlobalUnicast(ct.StringType("127.0.0.1")),
                         ct.BoolType(False))


# ---- CIDR ----

class CIDRTest(unittest.TestCase):
    def test_ipv4_cidr(self):
        result = cidr(ct.StringType("10.0.0.0/8"))
        self.assertIn("_cidr", result)
        self.assertEqual(result["family"], ct.IntType(4))
        self.assertEqual(result["prefixLength"], ct.IntType(8))

    def test_ipv6_cidr(self):
        result = cidr(ct.StringType("fd00::/64"))
        self.assertEqual(result["family"], ct.IntType(6))
        self.assertEqual(result["prefixLength"], ct.IntType(64))

    def test_passthrough_already_wrapped(self):
        wrapped = cidr(ct.StringType("10.0.0.0/8"))
        result = cidr(wrapped)
        self.assertEqual(result["family"], ct.IntType(4))


class IsCIDRTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(isCIDR(ct.StringType("10.0.0.0/8")),
                         ct.BoolType(True))

    def test_invalid(self):
        self.assertEqual(isCIDR(ct.StringType("nope")), ct.BoolType(False))


class ContainsIPTest(unittest.TestCase):
    def test_contained(self):
        net = cidr(ct.StringType("10.0.0.0/8"))
        addr = ip(ct.StringType("10.1.2.3"))
        self.assertEqual(containsIP(net, addr), ct.BoolType(True))

    def test_not_contained(self):
        net = cidr(ct.StringType("10.0.0.0/8"))
        addr = ip(ct.StringType("11.0.0.1"))
        self.assertEqual(containsIP(net, addr), ct.BoolType(False))


class ContainsCIDRTest(unittest.TestCase):
    def test_supernet(self):
        outer = cidr(ct.StringType("10.0.0.0/8"))
        inner = cidr(ct.StringType("10.1.0.0/16"))
        self.assertEqual(containsCIDR(outer, inner), ct.BoolType(True))

    def test_not_supernet(self):
        outer = cidr(ct.StringType("10.0.0.0/16"))
        inner = cidr(ct.StringType("10.0.0.0/8"))
        self.assertEqual(containsCIDR(outer, inner), ct.BoolType(False))


class PrefixLengthTest(unittest.TestCase):
    def test_from_string(self):
        self.assertEqual(prefixLength(ct.StringType("10.0.0.0/24")),
                         ct.IntType(24))


class MaskedTest(unittest.TestCase):
    def test_canonical_form(self):
        result = masked(ct.StringType("10.1.2.3/8"))
        self.assertEqual(str(result["cidr"]), "10.0.0.0/8")


if __name__ == "__main__":
    unittest.main()
