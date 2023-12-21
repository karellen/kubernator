# flake8: noqa
import os

ktor.app.register_plugin("minikube", k8s_version=os.environ["K8S_VERSION"],
                         start_fresh=bool(os.environ["START_FRESH"]),
                         keep_running=bool(os.environ["KEEP_RUNNING"]),
                         profile="full-smoke")
ktor.app.register_plugin("awscli")
ktor.app.register_plugin("terraform", version="1.5.7")
ktor.app.register_plugin("terragrunt", version="0.48.0")
ktor.app.register_plugin("k8s")
ktor.app.register_plugin("kubectl")
ktor.app.register_plugin("istio", version=os.environ["ISTIO_VERSION"])
ktor.app.register_plugin("helm", version="3.13.2")
ktor.app.register_plugin("templates")
