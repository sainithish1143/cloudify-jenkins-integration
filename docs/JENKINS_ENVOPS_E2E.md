# Cloudify Jenkins EnvOps E2E

This repo demonstrates Cloudify integration with Jenkins using the same files and scripts as the GitOps flow.

## Common model

```text
deployments/*.yaml  -> Cloudify environment desired state
operations/*.yaml   -> workflow execution intent
inputs/*.yaml       -> user/application input data
blueprints/**       -> Cloudify blueprint source
scripts/cloudify_lifecycle.py -> common Cloudify REST lifecycle runner
scripts/gitops_reconcile.py   -> common Git diff reconciler
```

Jenkins is only the trigger/orchestrator. It does not duplicate Cloudify lifecycle logic.

## Start Jenkins locally

```bash
cp .env.jenkins.example .env.jenkins
vi .env.jenkins
./reset-jenkins-e2e.sh
```

Open Jenkins:

```text
http://localhost:8080
```

Default login from `.env.jenkins`:

```text
admin / admin123
```

## Jobs

### cloudify-envops-manual

Manual/operator job. It uses the mounted repo and runs:

```bash
python3 scripts/manual_lifecycle_from_deployment.py ...
```

Examples:

```text
ACTION=create-environment
DEPLOYMENT_FILE=deployments/hello-dev.yaml
```

```text
ACTION=execute-workflow
DEPLOYMENT_FILE=deployments/hello-dev.yaml
WORKFLOW=install
```

```text
ACTION=execute-workflow
DEPLOYMENT_FILE=deployments/hello-dev.yaml
WORKFLOW=execute_operation
PARAMETERS_FILE=workflow-params/execute-configure.yaml
INJECT_INPUTS_AS_OPERATION_KWARGS=true
```

### cloudify-envops-git-polling

Git-triggered Jenkins job. Jenkins checks the configured repo, computes the Git diff, and runs:

```bash
python3 scripts/gitops_reconcile.py --before <old_sha> --after <new_sha>
```

This is the same commit-based mechanism as GitOps.

## Commit-based Jenkins demo

Create/reconcile environment:

```bash
echo "# jenkins env reconcile $(date)" >> deployments/hello-dev.yaml
git add deployments/hello-dev.yaml
git commit -m "Jenkins create hello dev Cloudify environment"
git push
```

Run install:

```bash
echo "# jenkins install $(date)" >> operations/hello-dev-install.yaml
git add operations/hello-dev-install.yaml
git commit -m "Jenkins run install workflow"
git push
```

Update input and run configure:

```bash
vi inputs/hello/dev.yaml
echo "# jenkins configure $(date)" >> operations/hello-dev-configure.yaml
git add inputs/hello/dev.yaml operations/hello-dev-configure.yaml
git commit -m "Jenkins run configure with updated inputs"
git push
```

Delete deployment:

```bash
git rm deployments/hello-dev.yaml
git commit -m "Jenkins remove hello dev Cloudify environment"
git push
```

## Production Jenkins

For production Jenkins, prefer Jenkins credentials and the provided `Jenkinsfile` / `Jenkinsfile.manual`.

Create Jenkins credentials:

```text
cfy-manager-url
cfy-username
cfy-password
cfy-tenant
```

Then configure a Pipeline job from SCM using `Jenkinsfile`.
