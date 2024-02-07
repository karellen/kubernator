# flake8: noqa
import os

phase = int(os.environ["TEST_PHASE"])
phase1 = (phase == 1)
phase2 = (phase == 2)

ktor.app.register_plugin("minikube", k8s_version=os.environ["K8S_VERSION"],
                         start_fresh=phase1, keep_running=phase1, profile="issue-17")
ktor.app.register_plugin("k8s")

if phase2:
    import logging
    import http.client as http_client

    http_client.HTTPConnection.debuglevel = 1
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True
