# flake8: noqa
import os

ktor.app.register_plugin("kind",
                         k8s_version=os.environ["K8S_VERSION"],
                         profile="multi-node",
                         nodes=5,
                         control_plane_nodes=3,
                         start_fresh=True,
                         keep_running=False)
ktor.app.register_plugin("k8s")
