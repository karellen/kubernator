# flake8: noqa
import os

ktor.app.register_plugin("kind",
                         k8s_version=os.environ["K8S_VERSION"],
                         profile="project-v1",
                         start_fresh=False,
                         keep_running=True)
ktor.app.register_plugin("k8s")
ktor.app.register_plugin("project", name="demo", cleanup=True)

ktor.k8s.add_resources("""
apiVersion: v1
kind: Namespace
metadata:
  name: demo-ns
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: root-cfg
  namespace: demo-ns
data:
  phase: "2"
""")
