# flake8: noqa
import os

ktor.app.register_plugin("kind",
                         k8s_version=os.environ["K8S_VERSION"],
                         profile="resource-generator",
                         start_fresh=True,
                         keep_running=True)
ktor.app.register_plugin("k8s")

_original_gen = ktor.k8s.resource_generator


def _filtered_gen():
    for resource in _original_gen():
        if resource.name != "cm-skip":
            yield resource


ktor.k8s.resource_generator = _filtered_gen
