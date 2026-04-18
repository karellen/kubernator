# flake8: noqa
ktor.app.project = "a"

ktor.k8s.add_resources("""
apiVersion: v1
kind: ConfigMap
metadata:
  name: a-cfg-1
  namespace: demo-ns
data:
  phase: "1"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: a-cfg-2
  namespace: demo-ns
data:
  phase: "1"
""")
