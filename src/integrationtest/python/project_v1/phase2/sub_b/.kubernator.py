# flake8: noqa
ktor.app.project = "b"

ktor.k8s.add_resources("""
apiVersion: v1
kind: ConfigMap
metadata:
  name: b-cfg-1
  namespace: demo-ns
data:
  phase: "2"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: b-cfg-2
  namespace: demo-ns
data:
  phase: "2"
""")
