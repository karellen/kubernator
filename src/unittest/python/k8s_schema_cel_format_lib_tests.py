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

from kubernator.plugins.k8s_schema.cel.extensions.format_lib import (
    _check_byte,
    _check_date,
    _check_datetime,
    _check_dns1035_label,
    _check_dns1123_label,
    _check_dns1123_subdomain,
    _check_label_value,
    _check_qualified_name,
    _check_uri,
    _check_uuid,
    named,
    namedFormat,
    validateFormat,
)


class DNS1123LabelTest(unittest.TestCase):
    def test_valid_label(self):
        self.assertEqual(_check_dns1123_label("my-app"), [])
        self.assertEqual(_check_dns1123_label("a"), [])

    def test_too_long(self):
        errs = _check_dns1123_label("a" * 64)
        self.assertTrue(any("63" in e for e in errs))

    def test_invalid_chars(self):
        errs = _check_dns1123_label("Bad_Name")
        self.assertTrue(errs)

    def test_starts_with_dash(self):
        errs = _check_dns1123_label("-starts-bad")
        self.assertTrue(errs)


class DNS1123SubdomainTest(unittest.TestCase):
    def test_valid_subdomain(self):
        self.assertEqual(_check_dns1123_subdomain("my.app.example.com"), [])
        self.assertEqual(_check_dns1123_subdomain("simple"), [])

    def test_too_long(self):
        errs = _check_dns1123_subdomain("a" * 254)
        self.assertTrue(any("253" in e for e in errs))

    def test_invalid_chars(self):
        errs = _check_dns1123_subdomain("Bad_Name.example.com")
        self.assertTrue(errs)


class DNS1035LabelTest(unittest.TestCase):
    def test_valid_label(self):
        self.assertEqual(_check_dns1035_label("my-app"), [])
        self.assertEqual(_check_dns1035_label("a"), [])

    def test_too_long(self):
        errs = _check_dns1035_label("a" * 64)
        self.assertTrue(any("63" in e for e in errs))

    def test_starts_with_digit(self):
        errs = _check_dns1035_label("1startsdigit")
        self.assertTrue(errs)


class QualifiedNameTest(unittest.TestCase):
    def test_simple_name(self):
        self.assertEqual(_check_qualified_name("my-name"), [])

    def test_prefixed_name(self):
        self.assertEqual(_check_qualified_name("example.com/my-name"), [])

    def test_multiple_slashes(self):
        errs = _check_qualified_name("a/b/c")
        self.assertTrue(errs)

    def test_empty_prefix(self):
        errs = _check_qualified_name("/my-name")
        self.assertTrue(any("prefix" in e for e in errs))

    def test_empty_name_part(self):
        errs = _check_qualified_name("example.com/")
        self.assertTrue(any("name part" in e for e in errs))

    def test_name_too_long(self):
        errs = _check_qualified_name("a" * 64)
        self.assertTrue(any("63" in e for e in errs))

    def test_name_invalid_chars(self):
        errs = _check_qualified_name("name with spaces")
        self.assertTrue(errs)


class LabelValueTest(unittest.TestCase):
    def test_valid_value(self):
        self.assertEqual(_check_label_value("my-label_value.1"), [])
        self.assertEqual(_check_label_value(""), [])

    def test_too_long(self):
        errs = _check_label_value("a" * 64)
        self.assertTrue(any("63" in e for e in errs))

    def test_invalid_chars(self):
        errs = _check_label_value("bad value!")
        self.assertTrue(errs)


class URITest(unittest.TestCase):
    def test_valid_uri(self):
        self.assertEqual(_check_uri("https://example.com/path"), [])
        self.assertEqual(_check_uri("http://example.com"), [])

    def test_forbidden_chars(self):
        errs = _check_uri("https://example.com/bad path")
        self.assertTrue(errs)

    def test_no_scheme(self):
        errs = _check_uri("example.com/path")
        self.assertTrue(any("scheme" in e for e in errs))


class UUIDTest(unittest.TestCase):
    def test_valid_uuid(self):
        self.assertEqual(_check_uuid("550e8400-e29b-41d4-a716-446655440000"), [])

    def test_invalid_uuid(self):
        errs = _check_uuid("not-a-uuid")
        self.assertTrue(errs)


class ByteTest(unittest.TestCase):
    def test_valid_base64(self):
        self.assertEqual(_check_byte("SGVsbG8="), [])

    def test_invalid_base64(self):
        errs = _check_byte("not-valid-base64!!!")
        self.assertTrue(errs)


class DateTest(unittest.TestCase):
    def test_valid_date(self):
        self.assertEqual(_check_date("2026-04-18"), [])

    def test_invalid_format(self):
        errs = _check_date("04/18/2026")
        self.assertTrue(errs)

    def test_invalid_date_values(self):
        errs = _check_date("2026-02-30")
        self.assertTrue(errs)


class DateTimeTest(unittest.TestCase):
    def test_valid_datetime_z(self):
        self.assertEqual(_check_datetime("2026-04-18T12:00:00Z"), [])

    def test_valid_datetime_offset(self):
        self.assertEqual(_check_datetime("2026-04-18T12:00:00+05:00"), [])

    def test_valid_datetime_fractional(self):
        self.assertEqual(_check_datetime("2026-04-18T12:00:00.123Z"), [])

    def test_invalid_format(self):
        errs = _check_datetime("2026-04-18 12:00:00")
        self.assertTrue(errs)


class NamedFormatAPITest(unittest.TestCase):
    def test_named_returns_map(self):
        result = named(ct.StringType("dns1123Label"))
        self.assertIsInstance(result, ct.MapType)
        self.assertEqual(str(result["name"]), "dns1123Label")

    def test_named_unknown_raises(self):
        with self.assertRaises(ValueError):
            named(ct.StringType("nonExistentFormat"))

    def test_namedFormat_is_alias(self):
        result = namedFormat(ct.StringType("uuid"))
        self.assertIsInstance(result, ct.MapType)

    def test_validateFormat_valid(self):
        matcher = named(ct.StringType("dns1123Label"))
        errs = validateFormat(matcher, ct.StringType("ok-name"))
        self.assertIsInstance(errs, ct.ListType)
        self.assertEqual(len(errs), 0)

    def test_validateFormat_invalid(self):
        matcher = named(ct.StringType("dns1123Label"))
        errs = validateFormat(matcher, ct.StringType("Bad_Name"))
        self.assertIsInstance(errs, ct.ListType)
        self.assertGreater(len(errs), 0)


if __name__ == "__main__":
    unittest.main()
