# Kubernator — Project Instructions

Pluggable framework for Kubernetes state management. CLI that walks directories, runs
per-directory `.kubernator.py` scripts, and generates/validates/transforms/applies K8s
resources through a plugin pipeline.

## Layout

PyBuilder project — standard `src/main/python`, `src/unittest/python`,
`src/integrationtest/python` tree.

- `src/main/python/kubernator/` — core package
  - `__init__.py` — entrypoint; `main()` **must** run `gevent.monkey.patch_all()` before
    importing `app`. `__version__` is templated (`${dist_version}`) and filled at build
    time by the `filter_resources` plugin.
  - `__main__.py`, `app.py` — CLI wiring and the plugin-driven stage pipeline
  - `api.py` — plugin-facing API (`ktor.*`), context hierarchy, Jinja env, JSON schema,
    diff-match-patch, HTTP, etc.
  - `merge.py`, `_json_path.py`, `_k8s_client_patches.py`, `proc.py` — internals
  - `plugins/` — `awscli`, `eks`, `gke`, `helm`, `istio`, `k8s`, `k8s_api`, `k3d`,
    `k8s_schema/`, `kind`, `kubeconfig`, `kubectl`, `minikube`, `project`, `template`,
    `terraform`, `terragrunt`
  - `plugins/k8s_schema/` — OpenAPI validation extracted out of `k8s.py` / `k8s_api.py`.
    `make_validator(ctx, …)` returns either a `SwaggerV2Validator` or an
    `OpenAPIV3Validator`. Factory default is `openapi_version="auto"` (v3 on server
    ≥ 1.27 with v2 fallback). The v3 path fetches the discovery index cluster-first
    (GitHub fallback), lazily fetches per-group sub-documents, enforces K8s extension
    keywords (`x-kubernetes-list-type`, `x-kubernetes-preserve-unknown-fields`,
    `x-kubernetes-embedded-resource`, `x-kubernetes-int-or-string`), and evaluates
    `x-kubernetes-validations` CEL rules via `cel-python` + ported K8s extension
    libraries (lists, regex, format, quantity, IP, CIDR) under `cel/extensions/`.
- `src/unittest/python/` — pytest-style unit tests (`*_tests.py`)
- `src/integrationtest/python/` — cram-style integration tests, many organized by
  `issue_NN/` reproducing specific bugs
- `Dockerfile` — ships `ghcr.io/karellen/kubernator` image built from the wheel in
  `target/dist/kubernator*/dist/`; pre-caches K8s clients for API versions 19–29

## Build / Test

PyBuilder per global instructions. Always use `pyb -vX` (verbose + debug output) for
all build invocations, including subset tasks (e.g. `pyb -vX run_unit_tests`).

Key bits specific to this repo:

- `coverage_break_build = False` and `cram_fail_if_no_tests = False` — build does not
  fail on coverage thresholds or empty cram dirs. Do not assume failures surface there.
- Integration tests inherit the environment (`integrationtest_inherit_environment = True`).
- Python 3.10–3.14 supported; CI matrix runs all of them on `ubuntu-latest`. Deployment
  (PyPI + GHCR) happens only from `push` events on Python 3.13 / Linux.
- Docker image is built by the custom `publish` task in `build.py` (not `distutils`):
  tags `:<dist_version>` always, plus `:latest` only on non-dev builds. `upload` task
  pushes all tags.

## Architecture notes worth preserving

- **gevent monkeypatch is load-bearing.** `main()` must patch before any stdlib
  networking is imported. Do not import `app` at module top level in `__init__.py`.
- **Context hierarchy follows directory traversal.** Values set in `/a` are visible in
  `/a/b`, `/a/c/d`, etc. `ctx.globals` is the always-available top context. Remote
  repos entered via `walk_remote` attach as children of the directory that registered
  them. When adding a feature that reads/writes context, decide explicitly which scope
  it belongs to.
- **Stage pipeline order:** Plugin Init → pre-start script → Plugin Start → per dir
  (Before Dir → [Before Script → `.kubernator.py` → After Script] → After Dir) →
  Plugin End. Plugin registration order determines handler execution order.
- **App plugin directory ordering:** scans children alphabetically, filters by
  `context.app.excludes`, then re-orders the remainder by `context.app.includes` pattern
  order. Tests touching traversal should cover both exclude and include interaction.
- **Project segments live in `App`, not on `.app`.** `context.app` is a single
  shared `PropertyDict` inherited across every directory context (writes to
  `cwd`/`includes`/`excludes` during `handle_before_dir` overwrite the shared
  slot on entry and `handle_after_dir` clears transient fields). Per-directory
  project segments are stored inside `App._project_segments`, keyed by the
  directory's `PropertyDict` context. `ktor.app.project` reads/writes go through
  a `ContextProperty` installed at `globals.app.project` whose `fget`/`fset`
  are `App._get_project` / `App._set_project`; both use `self.context` (the App's
  current directory context) to compose segments up the context chain or to
  store the new segment on the current directory. Segment regex is
  `[A-Za-z0-9_\-]+` (no dots, no special characters). `PropertyDict` supports
  this via a minimal descriptor protocol — see `ContextProperty` in `api.py`.
- **Project plugin is a switch.** Registering `project` populates
  `context.globals.project = {root, cleanup, state_namespace}`. All tagging,
  filtering, state Secret I/O, Lease locking, and cleanup live inside the k8s
  plugin and gate at runtime on the presence of `globals.project`. Register the
  project plugin *before* any resources are added — `project.register()` raises
  when `k8s.resources` is non-empty.
- **Project state Secret — one per root.** The k8s plugin stores a gzipped JSON
  payload inside a single `Secret` named `kubernator-project-<sha1(root)[:12]>`
  of type `kubernator.io/project-state`, in the configured `state_namespace`
  (default `kubernator-system`). Two-phase write: pre-apply sets
  `pending=new_intent, finalized=false`; post-cleanup sets `resources=...,
  finalized=true`. A run that crashes mid-flight leaves `finalized=false`; the
  next run's cleanup takes the conservative union (resources ∪ pending) so no
  previously-owned resource leaks.
- **Cluster lock via Lease.** `coordination.k8s.io/v1.Lease` named
  `kubernator-project-<sha1(root)[:12]>-lock` serializes concurrent project
  runs against the same root. Acquired at the start of `k8s.handle_apply`,
  renewed every 20 s by a gevent greenlet, released in `k8s.handle_shutdown`
  (always-fires). Stale leases (expired `renewTime + leaseDurationSeconds`)
  are taken over; fresh leases fail the incoming run fast.
- **`handle_cleanup` lifecycle stage.** Runs after `handle_verify` and before
  `handle_shutdown`. Verify failures abort before cleanup so a future rollback
  feature only has to undo applies/patches.

## Conventions

- File headers follow the `pybuilder_header_plugin_expected_header` in `build.py`
  (Apache-2.0, Express Systems USA / Karellen copyright). `break_build = False`, but
  new files should still carry the header.
- Release workflow: tag `[release]` / `[release <version>]` on the commit/PR subject
  per the global PyBuilder instructions. CI uses `release-app-id` /
  `release-app-private-key` secrets to bypass branch protection on release bumps.

## Issue-driven integration tests

Reproducers live at `src/integrationtest/python/issue_<N>/`. When fixing a bug, prefer
adding a new `issue_<N>/` directory that reproduces it rather than modifying an
existing one — this matches the established pattern and keeps regressions isolated.
