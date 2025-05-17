# flake8: noqa
import os

ktor.app.register_plugin("minikube", k8s_version=os.environ["K8S_VERSION"],
                         start_fresh=bool(os.environ["START_FRESH"]),
                         keep_running=bool(os.environ["KEEP_RUNNING"]),
                         profile="issue-68")
ktor.app.register_plugin("k8s")
ktor.app.register_plugin("istio", version=os.environ["ISTIO_VERSION"])
ktor.app.register_plugin("templates")

