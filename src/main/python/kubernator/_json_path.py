# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2024 Karellen, Inc.
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

import re
from functools import cache

from jsonpath_ng import JSONPath, DatumInContext
from jsonpath_ng.ext import parse as jp_parse, parser
from jsonpath_ng.ext.string import DefintionInvalid

__all__ = ["jp", "JPath"]


class JPath:
    def __init__(self, pattern):
        self.pattern = jp_parse(pattern)

    def find(self, val):
        return self.pattern.find(val)

    def all(self, val):
        return list(map(lambda x: x.value, self.find(val)))

    def first(self, val):
        """Returns the first element or None if it doesn't exist"""
        try:
            return next(map(lambda x: x.value, self.find(val)))
        except StopIteration:
            return None

    def only(self, val):
        """Returns the first and only element.
        Raises ValueError if more than one value found
        Raises KeyError if no value found
        """
        m = map(lambda x: x.value, self.find(val))
        try:
            v = next(m)
        except StopIteration:
            raise KeyError("no value found")
        try:
            next(m)
            raise ValueError("more than one value returned")
        except StopIteration:
            return v


@cache
def jp(pattern) -> JPath:
    return JPath(pattern)


MATCH = re.compile(r"match\(/(.*)(?<!\\)/\)")


class Match(JSONPath):
    """Direct node regex matcher

    Concrete syntax is '`match(/regex/)`'
    """

    def __init__(self, method=None):
        m = MATCH.match(method)
        if m is None:
            raise DefintionInvalid("%s is not valid" % method)
        self.expr = m.group(1).strip()
        self.regex = re.compile(self.expr)
        self.method = method

    def find(self, datum):
        datum = DatumInContext.wrap(datum)

        if hasattr(datum.path, "fields") and self.regex.match(datum.path.fields[0]):
            return [datum]
        return []

    def __eq__(self, other):
        return isinstance(other, Match) and self.method == other.method

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.method)

    def __str__(self):
        return '`match(/%s/)`' % (self.expr,)


old_p_jsonpath_named_operator = parser.ExtentedJsonPathParser.p_jsonpath_named_operator


def p_jsonpath_named_operator(self, p):
    "jsonpath : NAMED_OPERATOR"
    if p[1].startswith("match("):
        p[0] = Match(p[1])
    else:
        old_p_jsonpath_named_operator(self, p)


parser.ExtentedJsonPathParser.p_jsonpath_named_operator = p_jsonpath_named_operator
