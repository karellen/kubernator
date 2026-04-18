# Kubernator

Kubernator™ (Ktor™) is an integrated solution for the Kubernetes state management. It operates on directories,
processing their content via a collection of plugins, generating Kubernetes resources in the process, validating them,
transforming them and then applying against the Kubernetes cluster.

[![Gitter](https://img.shields.io/gitter/room/karellen/lobby?logo=gitter)](https://gitter.im/karellen/Lobby)
[![Build Status](https://img.shields.io/github/actions/workflow/status/karellen/kubernator/kubernator.yml?branch=master)](https://github.com/karellen/kubernator/actions/workflows/kubernator.yml)
[![Coverage Status](https://img.shields.io/coveralls/github/karellen/kubernator/master?logo=coveralls)](https://coveralls.io/r/karellen/kubernator?branch=master)

[![Kubernator Version](https://img.shields.io/pypi/v/kubernator?logo=pypi)](https://pypi.org/project/kubernator/)
[![Kubernator Python Versions](https://img.shields.io/pypi/pyversions/kubernator?logo=pypi)](https://pypi.org/project/kubernator/)
[![Kubernator Downloads Per Day](https://img.shields.io/pypi/dd/kubernator?logo=pypi)](https://pypi.org/project/kubernator/)
[![Kubernator Downloads Per Week](https://img.shields.io/pypi/dw/kubernator?logo=pypi)](https://pypi.org/project/kubernator/)
[![Kubernator Downloads Per Month](https://img.shields.io/pypi/dm/kubernator?logo=pypi)](https://pypi.org/project/kubernator/)

## Notices

### Beta Software

While fully functional in the current state and used in production, this software is in **BETA**. A lot of things
are expected to change rapidly, including main APIs, initialization procedures and some core features. Documentation at
this stage is basically non-existent.

### License

The product is licensed under the Apache License, Version 2.0. Please see LICENSE for further details.

### Warranties and Liability

Kubernator and its plugins are provided on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
express or implied, including, without limitation, any warranties or conditions of TITLE, NON-INFRINGEMENT,
MERCHANTABILITY, or FITNESS FOR A PARTICULAR PURPOSE. You are solely responsible for determining the appropriateness of
using or redistributing Kubernator and assume any risks associated with doing so.

### Trademarks

"Kubernator" and "Ktor" are trademarks or registered trademarks of Express Systems USA, Inc and Karellen, Inc. All other
trademarks are property of their respective owners.

## Problem Statement

Real-world Kubernetes deployments are rarely a flat pile of YAML files. A single environment typically combines:

- plain Kubernetes manifests kept under version control,
- Helm charts from public and private repositories (including OCI),
- Istio meshes installed via operator manifests,
- Custom Resource Definitions shipped separately from the resources that consume them,
- infrastructure outputs from Terraform or Terragrunt (VPC IDs, cluster endpoints, ARNs),
- credentials and kubeconfig files that differ per environment (EKS, GKE, Minikube, bare clusters),
- Jinja-rendered templates with values that must be shared across many resources,
- chunks of configuration that live in other git repositories and must be pulled in at deploy time.

Tools that cover one piece of this well (`kubectl`, `helm`, `kustomize`, `helmfile`, `terraform`) each have their own
state model, their own templating semantics, and their own assumptions about where files live. Gluing them together
usually ends up as ad-hoc shell scripts that duplicate logic across environments, hide their dependencies, and are
difficult to test.

## Solution

Kubernator is a CLI that walks a directory tree, executes an optional `.kubernator.py` script in each directory, and
runs a pipeline of plugins that generate, transform, validate, and apply Kubernetes resources. The directory tree
defines structure; the scripts define composition; the plugins define capability.

Key properties:

- **Directory-driven.** The unit of organisation is a directory. Sub-directories inherit context from their parents,
  making environment overlays and per-service customisation natural.
- **Plugin pipeline.** Plugins are explicitly registered by the user (not auto-loaded) and run through well-defined
  stages: `init` → `start` → per-directory (`before_dir` → `before_script` → `.kubernator.py` → `after_script`
  → `after_dir`) → `apply` → `summary`. Registration order is execution order.
- **Hierarchical context.** A context object (`ktor`) follows directory traversal. Values set in `/a` are visible in
  `/a/b` and `/a/c/d`; values set in `/a/b` are invisible in `/a/c`. `ctx.globals` is always reachable.
- **Composability.** `ktor.app.walk_local(...)` and `ktor.app.walk_remote(...)` let a script pull in further local or
  remote directories, including specific refs of git repositories. Remote content enters the context tree as a child
  of the directory that queued it.
- **Dry-run by default.** Nothing is applied to a cluster unless `--yes` is passed. The default mode (`dump`) writes
  the diff / final manifests to stdout.
- **Resource-aware.** The Kubernetes plugin talks to the API server directly via the Python client, resolves CRDs,
  runs server-side field validation, and computes minimal patches instead of blindly re-applying.

## Installation

### Docker

```shell
$ docker run --mount type=bind,source="$(pwd)",target=/root,readonly -t ghcr.io/karellen/kubernator:latest
```

The image is tagged by version at `ghcr.io/karellen/kubernator:<version>` and `:latest` for the most recent non-dev
release. Kubernetes client libraries for API versions 19–29 are pre-cached inside the image.

### MacOS

```shell
$ brew install python@3.13
$ pip3.13 install kubernator
$ kubernator --version
```

### Linux

```shell
$ pip install kubernator
$ kubernator --version
```

Python 3.10 through 3.14 are supported. Some plugins (`awscli`, `eks`, `gke`) may require additional volume mounts or
environment variables for credentials and external tooling.

## Command Line Interface

```
kubernator [OPTIONS] [dump|apply]
```

| Option                               | Description                                                                    |
|--------------------------------------|--------------------------------------------------------------------------------|
| `--version`                          | Print version and exit.                                                        |
| `--clear-cache`                      | Clear the application cache and exit.                                          |
| `--clear-k8s-cache`                  | Clear the Kubernetes client library cache and exit.                            |
| `--pre-cache-k8s-client V [V ...]`   | Download and cache the specified Kubernetes client library major versions.     |
| `--pre-cache-k8s-client-no-patch`    | Skip Kubernator's client patches while pre-caching (diagnostic).               |
| `--log-format {human,json}`          | Log output format. Default `human`.                                            |
| `--log-file PATH`                    | Write logs to file instead of `stderr`.                                        |
| `-v, --verbose LEVEL`                | `CRITICAL`/`ERROR`/`WARNING`/`INFO`/`DEBUG`/`TRACE`. Default `INFO`.            |
| `-f, --file PATH`                    | Output file for generated manifests. Default `stdout`.                         |
| `-o, --output-format {json,json-pretty,yaml}` | Output format. Default `yaml`.                                       |
| `-p, --path PATH`                    | Starting directory. Default current directory.                                 |
| `--yes`                              | Actually apply changes. Without this flag Kubernator runs as a dry-run.        |
| `-I, --include-project PROJECT`      | Repeatable. Limit the run to the named project and its sub-tree. No-op unless the `project` plugin is registered. |
| `-X, --exclude-project PROJECT`      | Repeatable. Exclude the named project and its sub-tree. No-op unless the `project` plugin is registered. |
| `command`                            | `dump` (default) writes the computed plan; `apply` applies it to the cluster.  |

## Mode of Operation

On startup Kubernator parses command line arguments, initialises logging, discovers plugin modules (without activating
them), and registers the always-present `app` plugin. Every other plugin must be explicitly registered by a
`.kubernator.py` script via `ktor.app.register_plugin("<name>", **kwargs)`. The **order of `register_plugin` calls is
the order of handler execution** for subsequent stages.

The pipeline stages, in order, are:

1. **Plugin Init** — called once per plugin when it is registered.
2. **Plugin Start** — called once per plugin after init.
3. **For each directory** in the traversal queue:
    1. **Before Directory** — every registered plugin's `handle_before_dir`.
    2. If `.kubernator.py` is present:
        1. **Before Script** — every plugin's `handle_before_script`.
        2. The `.kubernator.py` script itself (executed with `ktor` and `logger` in globals).
        3. **After Script** — every plugin's `handle_after_script` (reverse order).
    3. **After Directory** — every plugin's `handle_after_dir` (reverse order).
4. **Apply** — every plugin's `handle_apply` (e.g. Kubernetes plugin pushes resources to the cluster when `--yes`).
5. **Verify** — every plugin's `handle_verify`.
6. **Cleanup** — every plugin's `handle_cleanup` (runs after verify, so verify failures prevent cleanup).
7. **Shutdown** — every plugin's `handle_shutdown` (cleanups, even on failure).
8. **Summary** — every plugin's `handle_summary` (on success only).

Within "for each directory", after `after_dir` fires, the app plugin scans the current directory for sub-directories,
filters them through `context.app.excludes`, re-orders the survivors according to `context.app.includes` patterns, and
appends them to the traversal queue. Scripts can also inject directories explicitly with `walk_local` / `walk_remote`.

## State / Context

A global state is carried through as the application runs. It is a hierarchy of `PropertyDict` objects that follows the
parent-child relationship of directory traversal. Given `/a/b`, `/a/c`, `/a/c/d`: a value set in `/a`'s context is
visible in all of `/a/b`, `/a/c`, `/a/c/d`; a value set in `/a/b` is visible only there; a value set in `/a/c` is
visible in `/a/c` and `/a/c/d` but not in `/a` or `/a/b`.

`context.globals` is the top-most context, reachable from any stage (including those not associated with a directory).
When traversal enters a remote directory (materialised as a local temp directory), the remote tree enters the context
hierarchy as a child of the directory that queued it.

Context also carries references to essential functions — not only data. In pre-start and `.kubernator.py` scripts the
context is available as the global variable `ktor`, and a `logger` named after the script location is also injected.

## Plugins

Plugins are auto-discovered at startup but **only the App plugin runs automatically**. Every other plugin is opted in
by the user with `ktor.app.register_plugin("<name>", **kwargs)`. A plugin may `assert_plugin("other")` during
registration to declare a hard dependency; some plugins register their prerequisites themselves (e.g. `terragrunt`
pulls in `terraform`, `eks` pulls in `awscli`).

The table below names the plugin (the string passed to `register_plugin`), its role, the external binary it needs (if
any), and whether Kubernator downloads that binary automatically given a version.

| Plugin       | Role                                                             | Binary       | Auto-download    |
|--------------|------------------------------------------------------------------|--------------|------------------|
| `app`        | Directory traversal, plugin lifecycle, core `ktor` API.          | —            | —                |
| `kubeconfig` | Sets/overrides the kubeconfig path used downstream.              | —            | —                |
| `kubectl`    | Thin wrapper around `kubectl`.                                   | `kubectl`    | Yes              |
| `awscli`     | Ensures an `aws` CLI is available; used by EKS.                  | `aws`        | Yes              |
| `eks`        | Generates a kubeconfig for an AWS EKS cluster.                   | (via awscli) | —                |
| `gke`        | Generates a kubeconfig for a Google GKE cluster.                 | `gcloud`     | No (must be on PATH) |
| `minikube`   | Provisions and manages a local Minikube cluster.                 | `minikube`   | Yes              |
| `kind`       | Provisions and manages a local kind (Kubernetes IN Docker) cluster. | `kind`    | Yes              |
| `k3d`        | Provisions and manages a local k3d (k3s in Docker) cluster.      | `k3d`        | Yes              |
| `terraform`  | Initialises Terraform and exposes its outputs as `ktor.tf`.      | `terraform`  | Yes              |
| `terragrunt` | Same as above, but via Terragrunt (wraps Terraform).             | `terragrunt` | Yes              |
| `k8s`        | Core Kubernetes plugin: loads, transforms, validates, applies.   | (API server) | —                |
| `helm`       | Renders Helm charts (classic repo and OCI) into K8s resources.   | `helm`       | Yes              |
| `istio`      | Installs and upgrades Istio via `istioctl`/IstioOperator.        | `istioctl`   | Yes              |
| `templates`  | Registers and renders Jinja2 templates that emit K8s resources.  | —            | —                |
| `project`    | Scopes, tracks ownership, and cleans up resources by a hierarchical project name. | — | — |

### App Plugin (`app`)

The App plugin traverses the directory structure, exposes essential functions through the context, and runs
`.kubernator.py` scripts. It is registered automatically and is the only plugin that is always active.

After each directory's `after_dir` stage the App plugin scans child directories, sorts them alphabetically, removes
those matching any pattern in `context.app.excludes`, and re-orders the remainder to match the order of patterns in
`context.app.includes`. For example, with children `/a/foo`, `/a/bal`, `/a/bar`, `/a/baz`, excludes `["f*"]`, and
includes `["baz", "*"]`, the resulting queue is `/a/baz`, `/a/bal`, `/a/bar`.

Scripts can override this queue explicitly via `walk_local` and `walk_remote`.

#### Context

* `ktor.app.args`
  > Parsed command-line arguments.
* `ktor.app.cwd`
  > Current directory being processed (only defined inside per-directory stages).
* `ktor.app.includes`, `ktor.app.excludes`
  > Mutable `Globs` sets of patterns for sub-directory filtering. Resettable per-directory.
* `ktor.app.default_includes`, `ktor.app.default_excludes`
  > Defaults applied at the start of every directory.
* `ktor.app.walk_local(*paths, keep_context=False)`
  > Schedule local paths to be traversed after the current directory. Relative paths resolve against the current
  > directory. With `keep_context=True` the new paths inherit the current context instead of a fresh child context.
* `ktor.app.walk_remote(repo, *path_prefixes, keep_context=False)`
  > Schedule paths inside a remote git repository. `repo` is a URL (optionally with `?ref=<branch|tag|sha>`). Absolute
  > `path_prefixes` are resolved relative to the repository root.
* `ktor.app.repository_credentials_provider(func)`
  > Register a callable that adjusts credentials/scheme per URL. `func(parsed_url)` returns
  > `(scheme, username, password)` (any element may be `None` to leave it unchanged). Useful for flipping `git://` to
  > `https://` with a token in CI while leaving developer checkouts on SSH.
* `ktor.app.register_plugin(name_or_class, **kwargs)`
  > Register and initialise a plugin. `name` is the plugin's registered identifier (e.g. `"k8s"`, `"helm"`).
* `ktor.app.assert_plugin(name, requester)`
  > Assert that a prerequisite plugin is registered; raises if not.
* `ktor.app.register_cleanup(handler)`
  > Register an object with a `.cleanup()` method to be invoked on shutdown.
* `ktor.app.run(cmd, stdout, stderr, **kwargs)`,
  `ktor.app.run_capturing_out(cmd, stderr, **kwargs)`,
  `ktor.app.run_passthrough_capturing(cmd, stderr, **kwargs)`
  > Subprocess helpers with integrated logging.
* `ktor.app.download_remote_file(logger, url, category, sub_category)`,
  `ktor.app.load_remote_file(logger, url, file_type, category, sub_category)`
  > HTTP download helpers with on-disk caching.
* `ktor.app.jp(path)`
  > JSONPath convenience helper bound to the core implementation.

### Kubeconfig Plugin (`kubeconfig`)

Centralises the kubeconfig path so that other plugins see a consistent value. Defaults to `$KUBECONFIG` or
`~/.kube/config`. Plugins that generate their own kubeconfig (e.g. `minikube`, `kind`, `k3d`, `eks`, `gke`) call `set(...)` on this
plugin; consumers that need to react to changes register a notifier.

#### Context

* `ktor.kubeconfig.kubeconfig`
  > Current kubeconfig path.
* `ktor.kubeconfig.set(path)`
  > Replace the kubeconfig path and notify all registered observers.
* `ktor.kubeconfig.register_change_notifier(callable)`
  > Callable is invoked whenever the path changes.

### Kubectl Plugin (`kubectl`)

Thin wrapper around `kubectl`. If the `k8s` plugin has determined the cluster's API version, `kubectl` auto-selects a
matching binary; otherwise pass `version="1.30.0"` (or similar) to `register_plugin`. Kubernator downloads the binary
from the official Kubernetes release mirror and caches it.

#### Context

* `ktor.kubectl.kubectl_file`, `ktor.kubectl.version`
* `ktor.kubectl.stanza()`
  > Base command list (kubectl binary + `--kubeconfig` if set). Extend with additional arguments.
* `ktor.kubectl.run(*args, **kwargs)`
  > Run `kubectl <args>`, streaming stdout to logs.
* `ktor.kubectl.run_capturing(*args, **kwargs)`
  > Run `kubectl <args>` and return captured stdout.
* `ktor.kubectl.get(resource_type, resource_name, namespace=None)`
  > Fetch a resource (or list of resources) as a Python dict/list.

### AWS CLI Plugin (`awscli`)

Ensures `aws` is available; downloads and extracts the official AWS CLI v2 bundle if necessary. Primarily consumed by
the `eks` plugin but also usable directly from scripts that need AWS calls.

#### Context

* `ktor.awscli.aws_file`, `ktor.awscli.version`
* `ktor.awscli.stanza(*args, output="json", region=None)`
  > Build a ready-to-exec AWS CLI command list with `--output` and (optionally) `--region`.

### EKS Plugin (`eks`)

Uses `awscli` to generate a temporary kubeconfig for an EKS cluster and pushes it into the `kubeconfig` plugin. Register
with `name=<cluster>` and `region=<aws-region>`. AWS credentials must be available in the environment.

#### Context

* `ktor.eks.kubeconfig`
  > Path to the generated temporary kubeconfig.

### GKE Plugin (`gke`)

Equivalent for Google Kubernetes Engine. Relies on `gcloud` being installed on the host (not auto-downloaded). Register
with `name`, `region`, and `project`.

#### Context

* `ktor.gke.kubeconfig`, `ktor.gke.name`, `ktor.gke.region`, `ktor.gke.project`, `ktor.gke.gcloud_file`

### Minikube Plugin (`minikube`)

Drives a local Minikube cluster for development or integration testing. Downloads the `minikube` binary if necessary,
starts a profile, and publishes the generated kubeconfig to the `kubeconfig` plugin. Typical registration:

```python
ktor.app.register_plugin("minikube",
                         k8s_version="1.30.0",
                         profile="my-dev",
                         start_fresh=True,
                         keep_running=False,
                         driver="docker",
                         nodes=1)
```

#### Context

* `ktor.minikube.version`, `ktor.minikube.k8s_version`, `ktor.minikube.profile`, `ktor.minikube.kubeconfig`
* `ktor.minikube.start_fresh`, `ktor.minikube.keep_running`, `ktor.minikube.nodes`, `ktor.minikube.driver`,
  `ktor.minikube.cpus`, `ktor.minikube.extra_args`, `ktor.minikube.extra_addons`
* `ktor.minikube.cmd(*args)` / `ktor.minikube.cmd_out(*args)`
  > Run a `minikube` subcommand, optionally capturing output.

### Kind Plugin (`kind`)

Drives a local kind cluster (Kubernetes IN Docker — upstream kubeadm binaries running inside Docker containers, with
real etcd and separate control-plane components). Downloads the `kind` binary, creates a cluster, and publishes the
exported kubeconfig to the `kubeconfig` plugin. Unlike Minikube, kind does not ship bundled addons such as CSI hostpath
or LoadBalancer controllers — install those separately in your `.kubernator.py` if you need them, the same way you
would on any upstream Kubernetes cluster.

```python
ktor.app.register_plugin("kind",
                         k8s_version="1.34.0",
                         profile="my-dev",
                         start_fresh=True,
                         keep_running=False,
                         nodes=5,
                         control_plane_nodes=3)
```

Node images default to `ghcr.io/karellen/kindest-node:v<k8s_version>` (pre-built by the `kindest-node-release` workflow
in this repo for every K8s release ≥ 1.29.0, multi-arch amd64/arm64). Override with `node_image_registry="kindest/node"`
to pull from upstream Docker Hub, or pass `node_image=...` for a specific image. Lifecycle maps `start`/`stop` onto
`docker start` / `docker stop` on the node containers (kind has no native start/stop subcommands); `keep_running=False`
stops containers without deleting them, and `start_fresh=True` deletes and recreates the cluster.

Multi-node HA is supported directly: `control_plane_nodes >= 2` causes kind to auto-spawn an haproxy load-balancer
container in front of the API servers. Additional knobs: `extra_port_mappings`, `feature_gates`, `runtime_config`, or
raw `config` YAML override.

#### Context

* `ktor.kind.version`, `ktor.kind.k8s_version`, `ktor.kind.profile`, `ktor.kind.kubeconfig`
* `ktor.kind.node_image`, `ktor.kind.node_image_registry`
* `ktor.kind.nodes`, `ktor.kind.control_plane_nodes`, `ktor.kind.provider` (`docker` or `podman`)
* `ktor.kind.start_fresh`, `ktor.kind.keep_running`
* `ktor.kind.cmd(*args)` / `ktor.kind.cmd_out(*args)`
  > Run a `kind` subcommand, optionally capturing output.

### k3d Plugin (`k3d`)

Drives a local [k3d](https://k3d.io) cluster (k3s in Docker — Rancher's lightweight Kubernetes distribution running
inside Docker containers). Downloads the `k3d` binary, creates a cluster, and publishes the exported kubeconfig to the
`kubeconfig` plugin. Like kind, k3d does not ship the same addon set as Minikube — install CSI drivers, ingress
controllers, etc. yourself in your `.kubernator.py` if needed. K3s does ship with Traefik, ServiceLB, and a
local-path-provisioner enabled by default; pass `k3s_server_args=["--disable=traefik", ...]` to opt out.

```python
ktor.app.register_plugin("k3d",
                         k8s_version="1.34.6",
                         profile="my-dev",
                         start_fresh=True,
                         keep_running=False,
                         nodes=5,
                         control_plane_nodes=3)
```

Node images default to `rancher/k3s:v<k8s_version>-k3s1` (multi-arch amd64/arm64, published per K8s patch by Rancher).
Override the suffix via `node_image_suffix="-k3s2"` when Rancher rebuilds for a given K8s version, or pass
`node_image=...` for a fully custom image. Lifecycle uses k3d's native `cluster start` / `cluster stop` subcommands
(no `docker start/stop` plumbing needed); `keep_running=False` stops the cluster without deleting it, and
`start_fresh=True` deletes and recreates the cluster.

Multi-server HA is supported directly: `control_plane_nodes >= 2` causes k3d to auto-spawn a `loadbalancer`-role
container in front of the API servers. Additional knobs: `extra_port_mappings` (rendered onto the loadbalancer node),
`feature_gates` and `runtime_config` (translated into `--kube-apiserver-arg=...` server-side flags),
`k3s_server_args` / `k3s_agent_args` (raw k3s args targeted at server / agent nodes), or a raw `config` YAML override
(passed to `--config` verbatim — schema is `k3d.io/v1alpha5` `Simple`).

Only the Docker provider is supported; k3d's experimental podman path is not offered.

#### Context

* `ktor.k3d.version`, `ktor.k3d.k8s_version`, `ktor.k3d.profile`, `ktor.k3d.kubeconfig`
* `ktor.k3d.node_image`, `ktor.k3d.node_image_registry`, `ktor.k3d.node_image_suffix`
* `ktor.k3d.nodes`, `ktor.k3d.control_plane_nodes`, `ktor.k3d.provider` (`docker`)
* `ktor.k3d.start_fresh`, `ktor.k3d.keep_running`
* `ktor.k3d.cmd(*args)` / `ktor.k3d.cmd_out(*args)`
  > Run a `k3d` subcommand, optionally capturing output.

### Terraform Plugin (`terraform`)

Runs `terraform init` + `terraform output -json` in the current directory and merges the outputs into `ktor.tf`, making
infrastructure values available to scripts. Pass `version="1.5.7"` to pin a Terraform version; Kubernator will
download the matching binary from HashiCorp.

#### Context

* `ktor.terraform.version`, `ktor.terraform.tf_file`, `ktor.terraform.stanza()`
* `ktor.tf`
  > Dictionary populated with Terraform outputs (merged across directories that invoked the plugin).

### Terragrunt Plugin (`terragrunt`)

Same shape as the Terraform plugin but invokes `terragrunt`. Registers `terraform` implicitly. Pass `version=...` to
pin a Terragrunt version; the binary is downloaded from GitHub releases.

#### Context

* `ktor.terragrunt.version`, `ktor.terragrunt.tg_file`, `ktor.terragrunt.stanza()`
* `ktor.tf` (shared with the Terraform plugin)

### Kubernetes Plugin (`k8s`)

The core of Kubernator. Connects to the cluster, resolves its API version, picks a compatible client library (from the
pre-cache or downloading on demand), and collects manifests from YAML files under each traversed directory. During the
`apply` stage it computes per-resource diffs, honours CRD schemas, retries on conflicts, and performs server-side or
client-side field validation according to configuration.

File discovery uses globs `*.yaml` / `*.yml` by default, configurable per-directory via `ktor.k8s.includes` and
`ktor.k8s.excludes`.

#### Context

* `ktor.k8s.default_includes`, `ktor.k8s.default_excludes`, `ktor.k8s.includes`, `ktor.k8s.excludes`
* `ktor.k8s.add_resources(manifests, source=None)` — register a list/iterable of manifests directly.
* `ktor.k8s.load_resources(path, file_type)` — load manifests from a local file (`"yaml"`/`"json"`).
* `ktor.k8s.load_remote_resources(url, file_type, file_category=None)` — load from a URL with caching.
* `ktor.k8s.load_crds(path, file_type)` / `ktor.k8s.load_remote_crds(url, file_type, file_category=None)` — register
  CRDs separately from consuming resources so their schemas are known during validation.
* `ktor.k8s.import_cluster_crds()` — pull CRDs that are already installed on the target cluster.
* `ktor.k8s.add_transformer(func)` / `ktor.k8s.remove_transformer(func)` — register a function
  `func(resources, resource)` that may mutate manifests before apply.
* `ktor.k8s.add_validator(func)` — register a validator run after transformation.
* `ktor.k8s.add_manifest_patcher(func)` — register a low-level manifest patcher.
* `ktor.k8s.add_resource_filter(predicate)` / `ktor.k8s.remove_resource_filter(predicate)` — register/remove a
  predicate `predicate(resource)` consulted by `resource_generator()`; returning `False` skips the resource.
  Used internally by the `project` plugin for `-I`/`-X` scoping, but available to any script that needs
  declarative filtering without overriding the generator.
* `ktor.k8s.get_api_versions()` — set of `(group, version)` tuples in use.
* `ktor.k8s.create_resource(manifest)` — wrap a manifest as a `K8SResource` without registering it.
* `ktor.k8s.resource(manifest)` — return a fully-wired `K8SResource` with API bindings populated, for
  imperative CRUD (`.get()`, `.create(dry_run=False)`, `.patch(...)`, `.delete(wait=True)`, `.watch()`)
  that bypasses the declarative apply lifecycle. Accepts a manifest `dict` or a single-document YAML string.
* `ktor.k8s.resource_generator()` — iterable of resources fed to the apply pipeline; override this on
  a subclass / wrap via context binding to filter or augment the set declaratively before apply.
* `ktor.k8s.client`, `ktor.k8s.server_version`, `ktor.k8s.server_git_version` — access the underlying Kubernetes client.
* `ktor.k8s.field_validation` (`"Ignore"`/`"Warn"`/`"Strict"`),
  `ktor.k8s.field_validation_warn_fatal`,
  `ktor.k8s.disable_client_patches`,
  `ktor.k8s.conflict_retry_delay` — behavioural knobs, all settable at `register_plugin` time.
* `ktor.k8s.openapi_version` (`"auto"`/`"v2"`/`"v3"`, default `"auto"`) — choose the OpenAPI dialect used for
  client-side validation. `auto` picks v3 on Kubernetes ≥ 1.27 (where v3 went GA) and falls back to v2
  on any v3 failure. v3 is lossless (honours `oneOf`/`anyOf`/`nullable`/`default`), enforces the K8s
  extensions (`x-kubernetes-list-type`, `-preserve-unknown-fields`, `-embedded-resource`,
  `-int-or-string`), and evaluates `x-kubernetes-validations` CEL rules (including
  `optional.of`/`optional.none` and the K8s CEL libraries for lists, regex, format, quantity, IP, CIDR)
  pre-flight. Transition rules fire against the cluster's current state at apply time.
* `ktor.k8s.openapi_source` (`"auto"`/`"cluster"`/`"github"`, default `"auto"`) — v3 discovery source.
  `auto` tries the cluster's `/openapi/v3` endpoint first and falls back to GitHub's
  `api/openapi-spec/v3/` at the cluster's git tag.
* `ktor.k8s.patch_field_excludes`, `ktor.k8s.immutable_changes` — advanced patch/diff controls.

### Helm Plugin (`helm`)

Renders Helm charts as Kubernetes resources and feeds them into the `k8s` pipeline. Files named `*.helm.yaml` /
`*.helm.yml` declare releases. Both classic HTTP chart repositories and OCI registries are supported. Register with
`version=...` to pin a Helm version (auto-downloaded) and optionally `check_chart_versions=True` to fail the build if a
pinned chart version is not the latest available in its repository.

Example `foo.helm.yaml`:

```yaml
repository: https://kubernetes-sigs.github.io/metrics-server
chart: metrics-server
version: 3.12.2
name: metrics-server
namespace: kube-system
```

OCI form:

```yaml
chart: oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller
name: arc
namespace: arc-systems
```

#### Context

* `ktor.helm.default_includes`, `ktor.helm.default_excludes`, `ktor.helm.includes`, `ktor.helm.excludes`
* `ktor.helm.helm_file`, `ktor.helm.stanza()`
* `ktor.helm.namespace_transformer` — if true, namespaced resources rendered without a `namespace:` receive the release
  namespace automatically.
* `ktor.helm.check_chart_versions`
* `ktor.helm.add_helm(chart, name, namespace, repository=None, version=None, values=None, values_file=None,
  include_crds=False)` — programmatic equivalent of a `*.helm.yaml` file.
* `ktor.helm.add_helm_template(template)` — add a release declaration as a dict.

### Istio Plugin (`istio`)

Installs and upgrades Istio using `istioctl` against an `IstioOperator` resource. Files matching `*.istio.yaml` /
`*.istio.yml` are treated as IstioOperator manifests. Register with `version=...` to pin `istioctl`.

#### Context

* `ktor.istio.default_includes`, `ktor.istio.default_excludes`, `ktor.istio.includes`, `ktor.istio.excludes`
* `ktor.istio.istioctl_file`, `ktor.istio.stanza()`
* `ktor.istio.test()` — run `istioctl version`, returning `(version_tuple, full_output_dict)`.

### Project Plugin (`project`)

Introduces hierarchical ownership, scoping, and cleanup for Kubernator-managed resources. Register once at the root with a `name` — that name becomes the root of the project tree. Sub-directories extend the tree by assigning `ktor.app.project = "<segment>"` in their `.kubernator.py`; segments are dot-joined top-down into the full project path (e.g. `demo.api.frontend`). Segment regex is `[A-Za-z0-9_\-]+` — no dots, no special characters. Must be registered **before** any resources are added; `project.register()` raises if the `k8s` plugin already has resources.

```python
ktor.app.register_plugin("k8s")
ktor.app.register_plugin("project", name="demo", cleanup=True)
# later, in a subdir
ktor.app.project = "api"
```

Once registered, the k8s plugin:

- stamps every applied resource with a `kubernator.io/project` annotation carrying the composed path;
- honours `-I`/`-X` CLI flags to scope the run to specific sub-trees (prefix match; combined as `candidates = known ∩ includes` then `in_scope = candidates − excludes`);
- records a per-root state Secret at `<state_namespace>/kubernator-project-<sha1(root)[:12]>` (default namespace `kubernator-system`) containing a gzipped JSON payload of the owned resources' idents;
- on each run, diffs the prior Secret against the current manifest set and (when `cleanup=True`) deletes resources that used to belong to an in-scope sub-project but no longer do;
- serialises concurrent runs against the same root via a `coordination.k8s.io/v1.Lease` named `kubernator-project-<sha1(root)[:12]>-lock` in the same namespace.

The Secret write is two-phase: before `apply` the new intent is recorded as `pending` with `finalized=false`; after successful apply + cleanup the finalized payload replaces it. A crash between the two phases leaves `finalized=false`; the next run's cleanup conservatively unions prior `resources ∪ pending`, so no previously-owned resource leaks.

#### `register_plugin` keyword arguments

* `name` *(required)* — segment assigned at the current context's `.app.project`. Also the root of the project tree when registered at the top level.
* `cleanup=False` — if `True`, delete resources present in the prior Secret but absent from the current in-scope manifests. If `False`, diffs are logged but nothing is deleted.
* `state_namespace="kubernator-system"` — namespace for the state Secret and the Lease. Auto-created by the k8s plugin on a committed (non-dry-run) invocation.

#### Context

* `ktor.app.project`
  > The composed project path at the current context, or `None` if no segment is set anywhere in the chain. Read-only unless you know what you're doing — the descriptor enforces single-assignment per context and validates segment syntax.

### Templates Plugin (`templates`)

Defines Jinja2 templates and renders them into Kubernetes resources. The plugin uses custom delimiters `{${ ... }$}`
for expressions and `{%$ ... %}` for blocks so that templates remain valid-looking YAML.

Files ending `*.tmpl.yaml` / `*.tmpl.yml` are processed in two modes:

- a top-level `define:` block registers named templates;
- a top-level `apply:` block renders named templates with supplied values and feeds the results into `k8s`.

Example `define.tmpl.yaml`:

```yaml
define:
  - name: test
    path: .test.tmpl.yaml
```

Example `.test.tmpl.yaml` (referenced above):

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: {${ values.name }$}
```

Example `apply.tmpl.yaml`:

```yaml
apply:
  - name: test
    values:
      name: ns1
```

Templates have access to the full context and to extra filters for JSON/YAML output (`to_json`, `to_yaml`,
`to_yaml_str_block`, `to_json_yaml_str_block`).

#### Context

* `ktor.templates.default_includes`, `ktor.templates.default_excludes`, `ktor.templates.includes`,
  `ktor.templates.excludes`
* `ktor.templates.render_template(name, source, values=())` — render a registered template, returning the rendered
  string.
* `ktor.templates.apply_template(name, values=(), source=None)` — render and register the result as K8s manifests.

## Examples

### A minimal Minikube + k8s pipeline

A `.kubernator.py` at the root of a directory containing YAML manifests:

```python
import os

ktor.app.register_plugin("minikube",
                         k8s_version=os.environ["K8S_VERSION"],
                         profile="dev",
                         start_fresh=True,
                         keep_running=False)
ktor.app.register_plugin("k8s")
```

Run a dry-run:

```shell
$ kubernator -p ./manifests
```

Apply for real:

```shell
$ kubernator -p ./manifests --yes apply
```

### Combining plugins

The `full_smoke` integration test illustrates a realistic mix:

```python
import os

ktor.app.register_plugin("minikube", k8s_version=os.environ["K8S_VERSION"],
                         start_fresh=bool(os.environ["START_FRESH"]),
                         keep_running=bool(os.environ["KEEP_RUNNING"]),
                         profile="full-smoke")
ktor.app.register_plugin("awscli")
ktor.app.register_plugin("terraform", version="1.5.7")
ktor.app.register_plugin("terragrunt", version="0.48.0")
ktor.app.register_plugin("k8s")
ktor.app.register_plugin("kubectl")
ktor.app.register_plugin("istio", version=os.environ["ISTIO_VERSION"])
ktor.app.register_plugin("helm", version="3.13.2")
ktor.app.register_plugin("templates")
```

### Adding a remote directory

```python
ktor.app.repository_credentials_provider(lambda r: ("ssh", "git", None))
ktor.app.walk_remote("git://repo.example.com/org/project?ref=dev", "/project")
```

### Adding a local directory

```python
ktor.app.walk_local("/home/username/local-dir")
```

### Using a transformer to enforce policy

```python
def remove_replicas(resources, r: "K8SResource"):
    if (r.group == "apps" and r.kind in ("StatefulSet", "Deployment")
            and "replicas" in r.manifest["spec"]):
        logger.warning("Resource %s in %s contains `replica` specification that will be removed. Use HPA!!!",
                       r, r.source)
        del r.manifest["spec"]["replicas"]


ktor.k8s.add_transformer(remove_replicas)
```

### Importing CRDs already installed on the cluster

```python
ktor.app.register_plugin("k8s")
ktor.k8s.import_cluster_crds()
```

### Loading CRDs from a sibling directory before consuming them

```python
ktor.k8s.load_crds(ktor.app.cwd / ".." / "crd" / "manifests.yaml", "yaml")
```
