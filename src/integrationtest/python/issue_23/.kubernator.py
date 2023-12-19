# flake8: noqa
import os

ktor.app.register_plugin("minikube", k8s_version=os.environ["K8S_VERSION"],
                         start_fresh=True, keep_running=False, profile="issue-23")
ktor.app.register_plugin("k8s")
ktor.app.register_plugin("istio", version=os.environ["ISTIO_VERSION"])
ktor.app.register_plugin("templates")
