# flake8: noqa
import os

ktor.app.register_plugin("kind",
                         k8s_version=os.environ["K8S_VERSION"],
                         profile="delete-create",
                         start_fresh=True,
                         keep_running=False)
ktor.app.register_plugin("k8s")

ktor.k8s.resource("""
apiVersion: batch/v1
kind: Job
metadata:
  name: pi
  namespace: default
spec:
  template:
    spec:
      containers:
      - name: pi
        image: perl:5.34.0
        command: ["perl", "-Mbignum=bpi", "-wle", "print bpi(2000)"]
      restartPolicy: Never
  backoffLimit: 4
""").create(dry_run=False)

ktor.k8s.add_resources("""
apiVersion: batch/v1
kind: Job
metadata:
  name: pi
  namespace: default
spec:
  template:
    spec:
      containers:
      - name: pi
        image: perl:5.34.0
        command: ["perl", "-Mbignum=bpi", "-wle", "print 0"]
      restartPolicy: Never
  backoffLimit: 4
""")
