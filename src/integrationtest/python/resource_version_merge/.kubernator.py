# flake8: noqa
import os

ktor.app.register_plugin("kind",
                         k8s_version=os.environ["K8S_VERSION"],
                         profile="resource-version-merge",
                         start_fresh=True,
                         keep_running=False)
ktor.app.register_plugin("k8s")

ktor.k8s.resource("""
apiVersion: v1
kind: ConfigMap
metadata:
  name: test
  namespace: default
data:
  a: b
""").create(dry_run=False)

ktor.k8s.add_resources("""
apiVersion: v1
kind: ConfigMap
metadata:
  name: test
  namespace: default
data:
  a: c
""")
