# flake8: noqa
import os

ktor.app.register_plugin("k3d",
                         k8s_version=os.environ["K8S_VERSION"],
                         profile="k3d-smoke",
                         start_fresh=True,
                         keep_running=False)
ktor.app.register_plugin("k8s")
