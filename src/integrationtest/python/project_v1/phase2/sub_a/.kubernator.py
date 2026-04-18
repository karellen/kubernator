# flake8: noqa
ktor.app.project = "a"

# Phase 2 drops a-cfg-2 — it should be deleted by the cleanup phase because
# prior-run state Secret recorded it for project "demo.a".
ktor.k8s.add_resources("""
apiVersion: v1
kind: ConfigMap
metadata:
  name: a-cfg-1
  namespace: demo-ns
data:
  phase: "2"
""")
