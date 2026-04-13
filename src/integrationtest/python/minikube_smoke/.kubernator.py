# flake8: noqa
import os

ktor.app.register_plugin("minikube",
                         k8s_version=os.environ["K8S_VERSION"],
                         profile="minikube-smoke",
                         start_fresh=True,
                         keep_running=False)
ktor.app.register_plugin("k8s")
