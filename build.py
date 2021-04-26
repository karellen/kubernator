# -*- coding: utf-8 -*-
#
# Copyright 2021 © Payperless
#


from pybuilder.core import (use_plugin, init, Author)

use_plugin("pypi:karellen_pyb_plugin", ">=0.0.1")
use_plugin("python.coveralls")

name = "kubernator"
version = "0.0.1.dev"

summary = "Kubernator is the a pluggable framework for K8S provisioning"
authors = [Author("Arcadiy Ivanov", "arcadiy@karellen.co")]
maintainers = [Author("Arcadiy Ivanov", "arcadiy@karellen.co")]
url = "https://github.com/karellen/kubernator"
urls = {
    "Bug Tracker": "https://github.com/karellen/kubernator/-/issues",
    "Source Code": "https://github.com/karellen/kubernator",
    "Documentation": "https://github.com/karellen/kubernator"
}
license = "Proprietary"

requires_python = ">=3.9"

default_task = ["analyze", "publish"]


@init
def set_properties(project):
    project.depends_on("gevent", ">=21.1.2")
    project.depends_on("kubernetes", "~=12.0")
    project.depends_on("openapi-schema-validator", "~=0.1")
    project.depends_on("openapi-spec-validator", "~=0.3")
    project.depends_on("json-log-formatter", "~=0.3")
    project.depends_on("appdirs", "~=1.4")
    project.depends_on("requests", "~=2.25")
    project.depends_on("jsonpatch", "~=1.32")
    project.depends_on("jsonpath-ng", "~=1.5")
    project.depends_on("jinja2", "~=2.11")
    project.depends_on("coloredlogs", "~=15.0")

    project.set_property("coverage_break_build", False)
    project.set_property("cram_fail_if_no_tests", False)

    project.set_property("integrationtest_inherit_environment", True)

    project.set_property("copy_resources_target", "$dir_dist/")
    project.get_property("copy_resources_glob").append("LICENSE")
    project.include_file("kubernator", "LICENSE")

    project.set_property("distutils_console_scripts", ["kubernator = kubernator:main"])
    project.set_property("distutils_setup_keywords", ["kubernetes", "k8s", "kube", "top", "provisioning"])

    project.set_property("distutils_classifiers", [
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.9",
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
