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

import logging
from collections.abc import Mapping
from pathlib import Path

from jsonschema import Draft7Validator, draft7_format_checker

from kubernator.api import (KubernatorPlugin, Globs, scan_dir, load_file, FileType, calling_frame_source,
                            validator_with_defaults, TemplateEngine, Template)

logger = logging.getLogger("kubernator.template")

TEMPLATE_SCHEMA = {
    "definitions": {
        "define": {
            "properties": {
                "define": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string"
                            },
                            "defaults": {
                                "additionalProperties": True,
                                "type": "object",
                                "default": {},
                                "description": "names and values of the default properties"
                            },
                            "path": {
                                "type": "string",
                                "description": "path to a template file"
                            },
                        },
                        "required": ["name", "path"]
                    }
                }
            }
        },
        "apply": {
            "properties": {
                "apply": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string"
                            },
                            "values": {
                                "additionalProperties": True,
                                "type": "object",
                                "default": {},
                                "description": "names and values of the rendering properties"
                            },
                        },
                        "required": ["name"]
                    }
                }
            }
        }
    },
    "allOf": [
        {"$ref": "#/definitions/define"},
        {"$ref": "#/definitions/apply"}
    ]
}

Draft7Validator.check_schema(TEMPLATE_SCHEMA)
TEMPLATE_VALIDATOR_CLS: type[Draft7Validator] = validator_with_defaults(Draft7Validator)
TEMPLATE_VALIDATOR: Draft7Validator = TEMPLATE_VALIDATOR_CLS(TEMPLATE_SCHEMA, format_checker=draft7_format_checker)


class TemplatePlugin(KubernatorPlugin):
    logger = logger

    _name = "templates"

    def __init__(self):
        self.context = None

        self.templates: dict[str, Template] = {}
        self.template_engine = TemplateEngine(logger)

    def set_context(self, context):
        self.context = context

    def handle_init(self):
        context = self.context
        context.globals.templates = dict(default_includes=Globs(["*.tmpl.yaml", "*.tmpl.yml"], True),
                                         default_excludes=Globs([".*"], True),
                                         render_template=self.render_template,
                                         apply_template=self.apply_template
                                         )

    def handle_before_dir(self, cwd: Path):
        context = self.context

        context.templates.default_includes = Globs(context.templates.default_includes)
        context.templates.default_excludes = Globs(context.templates.default_excludes)
        context.templates.includes = Globs(context.templates.default_includes)
        context.templates.excludes = Globs(context.templates.default_excludes)

        # Exclude Template YAMLs from K8S resource loading
        context.k8s.excludes.add("*.tmpl.yaml")
        context.k8s.excludes.add("*.tmpl.yml")

    def handle_after_dir(self, cwd: Path):
        context = self.context
        templates = context.templates

        for f in scan_dir(logger, cwd, lambda d: d.is_file(), templates.excludes, templates.includes):
            p = cwd / f.name
            display_p = context.app.display_path(p)
            logger.debug("Adding Kubernator template from %s", display_p)

            template_docs = load_file(logger, p, FileType.YAML, display_p)

            for template_doc in template_docs:
                self._process_template_doc(template_doc, display_p)

    def add_local_template(self, path):
        display_p = self.context.app.display_path(path)

        templates = load_file(logger, path, FileType.YAML, display_p)

        self.add_template(templates, display_p)

    def add_template(self, template_docs, source=None):
        if source is None:
            source = calling_frame_source()

        if isinstance(template_docs, Mapping):
            self._process_template_doc(template_docs, source)
        else:
            for template in template_docs:
                self._process_template_doc(template, source)

    def render_template(self, name, source, values=()) -> str:
        if name not in self.templates:
            raise ValueError(f"Template with a name {name} does not exist")

        template = self.templates[name]
        logger.debug("Rendering template %s from %s in %s", name, template.source, source)
        rendered_template = template.render(self.context, values)

        if self.template_engine.failures():
            raise ValueError(f"Unable to render template {name} from {template.source} in {source} "
                             "due to undefined required variables")

        return rendered_template

    def apply_template(self, name, values=(), source=None):
        if source is None:
            source = calling_frame_source()

        rendered_template = self.render_template(name, source, values)
        template = self.templates[name]
        logger.info("Applying template %s from %s", name, template.source)
        self.context.k8s.add_resources(rendered_template, source=template.source)

    def _process_template_doc(self, template_doc, source):
        logger.info("Processing Kubernator template from %s", source)
        errors = list(TEMPLATE_VALIDATOR.iter_errors(template_doc))
        if errors:
            for error in errors:
                self.logger.error("Error detected in Kubernator template from %s", source, exc_info=error)
            raise errors[0]

        for template in template_doc.get("define", ()):
            self._add_template(template, source)

        for apply in template_doc.get("apply", ()):
            self.apply_template(apply["name"], apply["values"], source)

    def _add_template(self, template, source):
        self._add_parsed_template(source, **{k.replace("-", "_"): v for k, v in template.items()})

    def _add_parsed_template(self, source, *, name, path, defaults):
        if name in self.templates:
            raise ValueError(f"Template with a name {name} already exists and cannot be overwritten")

        file = Path(path)
        if not file.is_absolute():
            file = self.context.app.cwd / file

        with open(file, "rt") as f:
            template = self.template_engine.from_string(f.read())

        self.templates[name] = Template(name, template, defaults, source=source, path=file)

    def __repr__(self):
        return "Template Plugin"
