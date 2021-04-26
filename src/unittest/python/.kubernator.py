ktor.app.repository_credentials_provider(lambda r: ("ssh", "git", None))
ktor.app.walk_remote("git://repo.example.com/org/project?ref=dev", "/project")

ktor.app.walk_local("/home/username/local-dir")


def remove_replicas(resources, r: "K8SResource"):
    if (r.group == "apps" and r.kind in ("StatefulSet", "Deployment")
            and "replicas" in r.manifest["spec"]):
        logger.warning("Resource %s in %s contains `replica` specification that will be removed. Use HPA!!!",
                       r, r.source)
        del r.manifest["spec"]["replicas"]


ktor.k8s.add_transformer(remove_replicas)
