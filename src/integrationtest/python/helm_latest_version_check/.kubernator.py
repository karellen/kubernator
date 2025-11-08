# flake8: noqa
import os

ktor.app.register_plugin("minikube", k8s_version=os.environ["K8S_VERSION"],
                         start_fresh=True, keep_running=False, profile="helm-latest-version-check")
ktor.app.register_plugin("k8s")
ktor.app.register_plugin("helm", version="3.19.0", check_chart_versions=True)
