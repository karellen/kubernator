# flake8: noqa
import os

ktor.app.register_plugin("kind", k8s_version=os.environ["K8S_VERSION"],
                         start_fresh=False,
                         keep_running=bool(os.environ.get("KEEP_RUNNING")),
                         profile="issue-openapi-v3")
ktor.app.register_plugin("k8s",
                         openapi_version=os.environ.get("OPENAPI_VERSION", "v3"))
ktor.k8s.load_crds(ktor.app.cwd / ".." / "crd" / "manifests.yaml", "yaml")
