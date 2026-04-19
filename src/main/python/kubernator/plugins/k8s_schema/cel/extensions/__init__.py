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

from kubernator.plugins.k8s_schema.cel.extensions import (cidr_lib,
                                                          format_lib,
                                                          ip_lib,
                                                          lists,
                                                          optional_lib,
                                                          quantity,
                                                          regex_lib)

_MODULES = (lists, regex_lib, format_lib, quantity, ip_lib, cidr_lib, optional_lib)


def register_all() -> list:
    """Returns a flat list of CEL callables pulled from each extension
    module's ``__all__`` — pass as
    ``celpy.Environment.program(ast, functions=...)``.

    celpy binds each function to its Python ``__name__`` and rewrites
    ``obj.method(arg)`` as ``method(obj, arg)``, so a single list entry
    covers both call shapes.
    """
    functions: list = []
    for module in _MODULES:
        for name in module.__all__:
            functions.append(getattr(module, name))
    return functions


__all__ = ["register_all"]
