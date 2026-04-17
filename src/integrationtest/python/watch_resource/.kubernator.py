# flake8: noqa
import os

ktor.app.register_plugin("kind",
                         k8s_version=os.environ["K8S_VERSION"],
                         profile="watch-resource",
                         start_fresh=True,
                         keep_running=True)
ktor.app.register_plugin("k8s")
