# Cloudify GitOps: Environment + Workflow Intent Model

This repo demonstrates a production-style Cloudify integration that can be triggered by GitHub Actions today and by Jenkins later using the same scripts.

## Core idea

```text
deployments/*.yaml commit  -> create/register Cloudify environment only
operations/*.yaml commit   -> execute the requested Cloudify workflow
deployments/*.yaml delete  -> uninstall/delete based on deletion policy
```

This avoids hardcoding `install` or `update` into GitOps. The user explicitly provides the Cloudify workflow name in an operation intent file.

## Repo layout

```text
.github/workflows/cloudify-envops.yml
scripts/
  cloudify_lifecycle.py
  gitops_reconcile.py
  manual_lifecycle_from_deployment.py
deployments/
  hello-dev.yaml
operations/
  hello-dev-install.yaml
  hello-dev-configure.yaml
  hello-dev-uninstall.yaml
blueprints/hello/
inputs/hello/dev.yaml
workflow-params/execute-configure.yaml
```

## GitHub setup

Use a self-hosted runner when Cloudify is on local Minikube, for example `http://192.168.49.2`.

Repository secrets:

```text
CFY_MANAGER_URL = http://192.168.49.2
CFY_USERNAME    = admin
CFY_PASSWORD    = admin
CFY_TENANT      = default_tenant
```

Repository variables:

```text
CFY_API_VERSION = v3.1
CFY_INSECURE = true
GITOPS_MULTI_DEPLOYMENT_MODE = all
```

## Demo flow

### 1. Create Cloudify environment

Commit the deployment desired-state file:

```bash
git add deployments/hello-dev.yaml
git commit -m "Create hello dev Cloudify environment"
git push
```

Action: uploads/registers blueprint and creates Cloudify deployment. It does not run `install`.

### 2. Execute install workflow

Commit operation intent:

```bash
git add operations/hello-dev-install.yaml
git commit -m "Run install workflow for hello dev"
git push
```

Action: executes the workflow from the operation file:

```yaml
workflow: install
```

### 3. Show user inputs in logs

Update user/demo inputs:

```bash
vi inputs/hello/dev.yaml
```

Then commit an operation intent. For configure demo:

```bash
git add inputs/hello/dev.yaml operations/hello-dev-configure.yaml
git commit -m "Run configure workflow with updated Git input values"
git push
```

The operation uses `execute_operation` and injects the latest input values as `operation_kwargs`, so Cloudify execution logs show the committed input values.

### 4. Execute any custom workflow

Create a new operation file:

```yaml
apiVersion: cloudify.windriver.com/v1
kind: CloudifyOperation

metadata:
  name: hello-dev-custom-workflow

spec:
  deployment_ref: deployments/hello-dev.yaml
  workflow: my_custom_workflow
  wait: true
  timeout_sec: 3600
  parameters:
    key1: value1
    key2: value2
```

Commit it:

```bash
git add operations/hello-dev-custom-workflow.yaml
git commit -m "Run custom Cloudify workflow"
git push
```

### 5. Delete deployment/environment

For demo, `deployments/hello-dev.yaml` has:

```yaml
deletion_policy: auto_uninstall_delete
```

So deleting the deployment file runs uninstall and deletes the Cloudify deployment:

```bash
git rm deployments/hello-dev.yaml
git commit -m "Remove hello dev Cloudify environment"
git push
```

For production, set:

```yaml
deletion_policy: manual
```

Then users must commit an explicit uninstall operation before removing the deployment file.

## Jenkins later

Jenkins should use the same scripts:

```bash
python3 scripts/gitops_reconcile.py --before <old_sha> --after <new_sha>
```

Manual Jenkins jobs should use:

```bash
python3 scripts/manual_lifecycle_from_deployment.py \
  --deployment deployments/hello-dev.yaml \
  --action execute-workflow \
  --workflow install
```

So Jenkins and GitOps share the same deployment model and lifecycle engine.

### Robust operation behavior

Operation intent files can now optionally include:

```yaml
spec:
  ensure_environment: true
```

Default is `true`. If the referenced Cloudify deployment does not exist yet, the runner uploads the blueprint and creates the deployment before executing the workflow. This makes commit-based demos safer when a deployment file and operation file are committed together, while still preserving the production model:

- `deployments/*.yaml` defines/registers the Cloudify environment.
- `operations/*.yaml` executes the user-selected Cloudify workflow.
- Deleting `deployments/*.yaml` performs uninstall/delete based on policy.

The runner also creates Cloudify-compatible blueprint archives with exactly one top-level directory, as required by Cloudify Manager.

## Multiple deployments / same blueprint

Yes, the same blueprint can be used to create many deployments with different inputs. Keep one file per deployment under `deployments/`, and point each deployment to its own input file. See `docs/MULTI_DEPLOYMENT_MODEL.md` and `examples/multi-deployment/`.

Example:

```text
blueprints/hello/blueprint.yaml
inputs/hello/app1-dev.yaml
inputs/hello/app2-dev.yaml
deployments/app1-dev.yaml
deployments/app2-dev.yaml
operations/app1-dev-install.yaml
operations/app2-dev-install.yaml
```

`deployments/*.yaml` creates/registers Cloudify environments. `operations/*.yaml` executes user-provided Cloudify workflow names. The same mechanism is suitable for Jenkins later because Jenkins can call the same scripts.


## Input values in Cloudify logs

The demo blueprint maps deployment inputs to node properties and the lifecycle script reads those properties. This means input values appear during normal lifecycle workflows such as `install`, not only during `execute_operation`. Operation kwargs can still override these values for ad-hoc workflow execution.

## Note on input logging fix

The demo lifecycle script now reads values from node properties mapped from deployment inputs and from execute_operation kwargs. It does not write runtime properties during lifecycle operations, which avoids Cloudify script-runner read-only property conflicts across versions.


## Important: stale Cloudify deployment protection

This demo package sets `spec.policies.force_recreate_environment: true` in `deployments/hello-dev.yaml`.
When the deployment file is committed, the reconciler uploads the latest blueprint and recreates the Cloudify deployment if it already exists.
This prevents old deployment plans from continuing to run an older blueprint script.

For production, set it to `false` and use an explicit Cloudify deployment-update or controlled migration workflow.


## Jenkins integration

This package is Jenkins-ready. Jenkins uses the same files and scripts as the GitOps flow:

```text
deployments/*.yaml
operations/*.yaml
inputs/*.yaml
blueprints/**
scripts/cloudify_lifecycle.py
scripts/gitops_reconcile.py
scripts/manual_lifecycle_from_deployment.py
```

Start local Jenkins E2E:

```bash
cp .env.jenkins.example .env.jenkins
vi .env.jenkins
./reset-jenkins-e2e.sh
```

Open `http://localhost:8080`. Jobs created automatically:

```text
cloudify-envops-manual
cloudify-envops-git-polling
```

See `docs/JENKINS_ENVOPS_E2E.md`.

## Jenkins/GitOps consistency note

This Jenkins package follows the same behavior as the GitOps package:

- Deployment YAML commit creates/reconciles the Cloudify environment.
- Operation YAML commit executes a Cloudify workflow.
- Input YAML alone is data-only and does not execute a workflow.
- Deployment YAML deletion removes the Cloudify environment based on the deployment policy.

For this demo, `deployments/hello-dev.yaml` uses `deletion_policy: delete_only` because the sample blueprint/environment may not expose a Cloudify `uninstall` workflow. Do not use `operations/*uninstall*.yaml` unless your blueprint explicitly provides that workflow.
