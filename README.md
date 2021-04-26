# Kubernator

Kubernator (Ktor) is an integrated solution for the Kubernetes state management. It operates on the directories, 
processing their content via a collection of plugins, generating Kubernetes resources in the process, validating them, 
transforming them and then applying against the Kubernetes cluster.

## Mode of Operation

Kubernator is a command line utility. Upon startup and processing of the command line arguments and initializing 
logging, Kubernator initializes plugins. Current plugins include:

0. Kubernator App
1. Terraform
2. kOps
3. Kubernetes
4. Helm
5. Template

The order of initialization matters as it's the order the plugin handlers are executed!

The entire application operates in the following stages by invoking each plugin's stage handler in sequence:

1. Plugin Init Stage
2. Pre-start script (if specified)
3. Plugin Start Stage
4. For each directory in the pipeline:
   1. Plugin Before Directory Stage
   2. If `.kubernator.py` is present in the directory: 
      1. Plugin Before Script Stage
      2. `.kubernator.py` script
      3. Plugin After Script Stage
   3. Plugin After Directory Stage
5. Plugin End Stage

Each plugin individually plays a specific role and performs a specific function which will be described in a later
section.

## State/Context

There is a global state that is carried through as the application is running. It is a hierarchy of objects (`context`)
that follows the parent-child relationship as the application traverses the directory structure.
For example, given the directory structure `/a/b`, `/a/c`, and `/a/c/d` any value of the context set or modified in
context scoped to directory `/a` is visible in directories `/a/b`, `/a/c` and `/a/c/d`, while the same modified or
set in `/a/b` is only visible there, while one in `/a/c` is visible in `/a/c` and in `/a/c/d` but not `/a` or `/a/b`.

Additionally, there is a `context.globals` which is the top-most context that is available in all stages that are not
associated with the directory structure.

Note, that in cases where the directory structure traversal moves to remote directories (that are actualized by local
temporary directories), such remote directory structure enters the context hierarchy as a child of the directory in 
which remote was registered.

Also note, that context carries not just data by references to essential functions.

In pre-start and `.kubernator.py` scripts the context is fully available as a global variable `ktor`.

### Plugins

#### Kubernator App Plugin

The role of the Kubernator App Plugin is to traverse the directory structure, expose essential functions through context
and to run Kubernator scripts.

In the *After Directory Stage* Kubernator app scans the directories immediately available in the current, sorts them
in the alphabetic order, excludes those matching any of the patterns in `context.app.excludes` and then queues up the 
remaining directories in the order the match the patterns in `context.app.includes`. 

Thus, for a directory content `/a/foo`, `/a/bal`, `/a/bar`, `/a/baz`, excludes `f*`, and includes `baz` and `*`, 
the resulting queue of directories to traverse will be `/a/baz`, `/a/bal`, `/a/bar`.

Notice, that user can further interfere with processing order of the directory queue by asking Kubernator to walk 
arbitrary paths, both local and remote.

##### Context

* `ktor.app.args`
  > Namespace containing command line argument values
* `ktor.app.walk_local(*paths: Union[Path, str, bytes])`
  > Immediately schedules the paths to be traversed after the current directory by adding them to the queue
  > Relative path is relative to the current directory
* `ktor.app.walk_remote(repo, *path_prefixes: Union[Path, str, bytes])`
  > Immediately schedules the path prefixes under the remote repo URL to be traversed after the current directory by 
  > adding them to the queue. Only Git URLs are currently supported.
  > All absolute path prefixes are relativized based on the repository.
* `ktor.app.repository_credentials_provider(func: Callable)`
  > Sets a repository credentials provider function `func` that sets/overwrites credentials for URLs being specified by
  > `walk_remote`. The callable `func` accepts a single argument containing a parsed URL in a form of tuple. The `func`
  > is expected to return a tuple of three elements representing URL schema, username and password. If the value should 
  > not be changed it should be None. To convert from `git://repo.com/hello` to HTTPS authentication one should write
  > a function returning `("https", "username", "password")`. The best utility is achieved by logic that allows running 
  > the plan both in CI and local environments using different authentication mechanics in different environments.

#### Terraform

This is exclusively designed to pull the configuration options out of Terraform and to allow scripts and plugins to 
utilize that data.

##### Context

* `ktor.tf`
  > A dictionary containing the values from Terraform output


#### Kops

##### Context


#### Kubernetes

##### Context


#### Helm

##### Context


#### Templates

##### Context


## Examples


### Adding Remote Directory

```python
ktor.app.repository_credentials_provider(lambda r: ("ssh", "git", None))
ktor.app.walk_remote("git://repo.example.com/org/project?ref=dev", "/project")
```

### Adding Local Directory

```python
ktor.app.walk_local("/home/username/local-dir")
```

### Using Transformers

```python
def remove_replicas(resources, r: "K8SResource"):
    if (r.group == "apps" and r.kind in ("StatefulSet", "Deployment")
            and "replicas" in r.manifest["spec"]):
        logger.warning("Resource %s in %s contains `replica` specification that will be removed. Use HPA!!!",
                       r, r.source)
        del r.manifest["spec"]["replicas"]


ktor.k8s.add_transformer(remove_replicas)
```
