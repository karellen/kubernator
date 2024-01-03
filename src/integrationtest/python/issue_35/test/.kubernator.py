# flake8: noqa
import os

ktor.app.register_plugin("minikube", k8s_version=os.environ["K8S_VERSION"],
                         start_fresh=False,
                         keep_running=os.environ["KEEP_RUNNING"], profile="issue-35")
ktor.app.register_plugin("k8s",
                         field_validation=os.environ["FIELD_VALIDATION"],
                         field_validation_warn_fatal=os.environ["WARN_FATAL"])
ktor.k8s.load_crds(ktor.app.cwd / ".." / "crd" / "manifests.yaml", "yaml")
