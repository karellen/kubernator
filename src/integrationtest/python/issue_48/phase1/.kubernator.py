# flake8: noqa
import os

ktor.app.register_plugin("minikube", k8s_version=os.environ["K8S_VERSION"],
                         start_fresh=True, keep_running=True, profile="issue-48")
ktor.app.register_plugin("k8s")

if False:
    _old_req = ktor.k8s.client.rest_client.pool_manager.request


    def request(method, url, fields=None, headers=None, **urlopen_kw):
        resp = _old_req(method, url, fields=fields, headers=headers, **urlopen_kw)
        logger.info("Send:\n%s %s\n\n%s\n\n%s",
                    method, url, "\n".join(map(lambda t: "%s: %s" % (t[0], t[1]), headers.items())),
                    urlopen_kw.get("body", ""))
        logger.info("Recv:\n%s %s\n\n%s\n\n%s",
                    resp.status, resp.reason, "\n".join(map(lambda t: "%s: %s" % (t[0], t[1]), resp.headers.items())),
                    resp.data.decode("utf-8"))
        return resp


    ktor.k8s.client.rest_client.pool_manager.request = request
