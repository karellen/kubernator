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

import textwrap

from pybuilder.core import (use_plugin, init, Author)

use_plugin("pypi:karellen_pyb_plugin", ">=0.0.1")
use_plugin("python.coveralls")

name = "kubernator"
version = "1.0.0.dev"

summary = "Kubernator is the a pluggable framework for K8S provisioning"
authors = [Author("Express Systems USA, Inc.", "")]
maintainers = [Author("Karellen, Inc.", "supervisor@karellen.co"),
               Author("Arcadiy Ivanov", "arcadiy@karellen.co")]

url = "https://github.com/karellen/kubernator"
urls = {
    "Bug Tracker": "https://github.com/karellen/kubernator/issues",
    "Source Code": "https://github.com/karellen/kubernator/",
    "Documentation": "https://github.com/karellen/kubernator/"
}
license = "Apache License, Version 2.0"

requires_python = ">=3.9"

default_task = ["analyze", "publish"]


@init
def set_properties(project):
    project.depends_on("gevent", ">=21.1.2")
    project.depends_on("kubernetes", "~=17.0")
    project.depends_on("openapi-schema-validator", "~=0.1")
    project.depends_on("openapi-spec-validator", "~=0.3")
    project.depends_on("json-log-formatter", "~=0.3")
    project.depends_on("appdirs", "~=1.4")
    project.depends_on("requests", "~=2.25")
    project.depends_on("jsonpatch", "~=1.32")
    project.depends_on("jsonpath-ng", "~=1.5")
    project.depends_on("jinja2", "~=3.1")
    project.depends_on("coloredlogs", "~=15.0")
    project.depends_on("jsonschema", "<4.0")

    project.set_property("coverage_break_build", False)
    project.set_property("cram_fail_if_no_tests", False)

    project.set_property("integrationtest_inherit_environment", True)

    project.set_property("copy_resources_target", "$dir_dist/kubernator")
    project.get_property("copy_resources_glob").append("LICENSE")
    project.include_file("kubernator", "LICENSE")

    project.set_property("distutils_upload_sign", False)
    project.set_property("distutils_upload_sign_identity", None)
    project.set_property("distutils_upload_repository_key", None)
    project.set_property("distutils_console_scripts", ["kubernator = kubernator:main"])
    project.set_property("distutils_setup_keywords", ["kubernetes", "k8s", "kube", "top", "provisioning",
                                                      "kOps", "terraform", "tf", "AWS"])

    project.set_property("distutils_classifiers", [
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX",
        "Operating System :: POSIX :: Linux",
        "Environment :: Console",
        "Topic :: Utilities",
        "Topic :: System :: Monitoring",
        "Topic :: System :: Distributed Computing",
        "Topic :: System :: Clustering",
        "Topic :: System :: Networking",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Developers",
        "Development Status :: 4 - Beta"
    ])
    project.set_property('pybuilder_header_plugin_break_build', False)
    project.set_property("pybuilder_header_plugin_expected_header",
                         textwrap.dedent("""\
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
                         """))
