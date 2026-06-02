# Cloudify EnvOps Integration

This repository demonstrates a production-style Cloudify integration model that can be triggered by either GitHub Actions GitOps or Jenkins while using the same files and the same scripts.

## Core model

```text
deployments/*.yaml commit/delete  -> create/delete Cloudify environment
operations/*.yaml commit          -> execute requested Cloudify workflow
inputs/*.yaml commit only         -> no workflow execution by itself
blueprints/**                     -> Cloudify blueprint source
scripts/**                        -> common lifecycle engine used by both GitOps and Jenkins
```

## Why this model

Cloudify blueprints may expose different workflows such as `install`, `execute_operation`, `heal`, `scale`, `backup`, `restore`, or customer-defined workflows. Therefore workflow execution is modeled explicitly through `operations/*.yaml` instead of hardcoding install/update/uninstall behavior.

## Main files

```text
blueprints/hello/blueprint.yaml          # demo Cloudify blueprint
blueprints/hello/scripts/lifecycle.py    # prints Git/Jenkins provided input values
deployments/hello-dev.yaml               # Cloudify environment desired state
inputs/hello/dev.yaml                    # input values for the deployment
operations/hello-dev-install.yaml        # executes install workflow
operations/hello-dev-configure.yaml      # executes execute_operation workflow
scripts/cloudify_lifecycle.py            # common Cloudify REST lifecycle runner
scripts/gitops_reconcile.py              # common Git diff reconciler
scripts/manual_lifecycle_from_deployment.py
```

## Demo sequence

### 1. Create environment

```bash
echo "# reconcile env $(date)" >> deployments/hello-dev.yaml
git add deployments/hello-dev.yaml
git commit -m "Create hello dev Cloudify environment"
git push
```

This uploads/reuses the blueprint and creates/reuses the deployment. It does not run install.

### 2. Execute install workflow

```bash
echo "# install $(date)" >> operations/hello-dev-install.yaml
git add operations/hello-dev-install.yaml
git commit -m "Run install workflow for hello dev"
git push
```

### 3. Update inputs and execute configure operation

```bash
vi inputs/hello/dev.yaml
echo "# configure $(date)" >> operations/hello-dev-configure.yaml
git add inputs/hello/dev.yaml operations/hello-dev-configure.yaml
git commit -m "Run configure workflow with updated inputs"
git push
```

The Cloudify execution logs should show `customer_name`, `application_name`, `environment`, `replicas`, and `message`.

### 4. Delete environment

```bash
git rm deployments/hello-dev.yaml
git commit -m "Remove hello dev Cloudify environment"
git push
```

With `deletion_policy: delete_only`, this deletes the Cloudify deployment without requiring an uninstall workflow.

## Multiple deployments using the same blueprint

The same blueprint can be reused by many deployments with different deployment IDs and input files:

```text
deployments/app1-dev.yaml -> inputs/hello/app1-dev.yaml -> deployment_id app1-dev
deployments/app2-dev.yaml -> inputs/hello/app2-dev.yaml -> deployment_id app2-dev
```

See `examples/multi-deployment/`.

## Production notes

- Keep secrets outside Git. Use GitHub Actions secrets or Jenkins credentials/env.
- Use `deletion_policy: manual` for stricter production deletion approval.
- Use `delete_only` when the blueprint does not expose an uninstall workflow.
- Use `auto_uninstall_delete` only when the blueprint exposes a valid uninstall workflow.
- Keep `force_recreate_environment: false` in production unless this is a demo or lab reset flow.
- Use new `blueprint.id` versions for breaking blueprint changes, or implement a controlled update/migration workflow.

## Jenkins setup

Create `.env.jenkins` from `.env.jenkins.example`, set Cloudify values and Jenkins repo URL, then run:

```bash
./reset-jenkins-e2e.sh
```

Open Jenkins at:

```text
http://localhost:8080
```

Jobs:

```text
cloudify-envops-git-polling
cloudify-envops-manual
```

The first polling run only captures the baseline. Push a new commit under `deployments/` or `operations/` after that to trigger Cloudify actions.
