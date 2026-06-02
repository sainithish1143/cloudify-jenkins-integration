# Demo naming and multi-deployment convention

This repository uses source-specific Cloudify object names so the Cloudify UI clearly shows where an object came from.

## Primary demo objects

- Blueprint ID: `wr-demo-jenkins-hello-bp`
- Deployment ID: `wr-demo-jenkins-hello`
- Deployment desired-state file: `deployments/wr-demo-jenkins-hello.yaml`
- Install operation file: `operations/wr-demo-jenkins-hello-install.yaml`
- Configure operation file: `operations/wr-demo-jenkins-hello-configure.yaml`

The deployment ID intentionally does **not** use a `-dev` or `_dev` suffix. The environment is tracked separately in `metadata.environment: dev` and in the input file.

## Multiple deployments from the same blueprint

The `examples/multi-deployment` directory contains two deployments using the same blueprint ID `wr-demo-jenkins-hello-bp` with different deployment IDs and input files:

- `wr-demo-jenkins-app1`
- `wr-demo-jenkins-app2`

Copy the example files into the repo root folders to test them:

```bash
cp examples/multi-deployment/inputs/hello/wr-demo-jenkins-app1.yaml inputs/hello/
cp examples/multi-deployment/deployments/wr-demo-jenkins-app1.yaml deployments/
cp examples/multi-deployment/operations/wr-demo-jenkins-app1-install.yaml operations/
cp examples/multi-deployment/operations/wr-demo-jenkins-app1-configure.yaml operations/

git add inputs/hello/wr-demo-jenkins-app1.yaml deployments/wr-demo-jenkins-app1.yaml operations/wr-demo-jenkins-app1-install.yaml
git commit -m "Create wr-demo-jenkins-app1 and run install"
git push
```

## Uninstall operation support

Optional uninstall operation samples are provided with `.yaml.sample` extension so they do not execute accidentally. Rename one to `.yaml` only when the target blueprint/deployment exposes an `uninstall` workflow.

For desired-state deletion, prefer deleting the deployment file:

```bash
git rm deployments/wr-demo-jenkins-hello.yaml
git commit -m "Remove wr-demo-jenkins-hello Cloudify environment"
git push
```
