# Cloudify Jenkins Integration - Production V3 Visible Package

This package is the Jenkins counterpart of the GitOps V3 package. It uses the same common Cloudify execution model and the same script structure.

## Naming convention

Jenkins-created Cloudify objects use the `wr-demo-jenkins-*` prefix.

Default demo objects:

- Blueprint ID: `wr-demo-jenkins-hello-bp`
- Deployment ID: `wr-demo-jenkins-hello`
- Deployment file: `deployments/wr-demo-jenkins-hello.yaml`

Multi-deployment examples:

- `wr-demo-jenkins-app1`
- `wr-demo-jenkins-app2`

## Behavior

- `deployments/*.yaml` add/modify: create/reconcile Cloudify environment.
- `operations/*.yaml` add/modify: execute the requested Cloudify workflow.
- `inputs/*.yaml` only: data-only change; no workflow execution by itself.
- `deployments/*.yaml` delete: delete Cloudify environment based on policy.

## Same model as GitOps

The Jenkins repo uses the same core scripts and YAML model as the GitOps repo:

- `scripts/cloudify_lifecycle.py`
- `scripts/gitops_reconcile.py`
- `scripts/manual_lifecycle_from_deployment.py`
- `deployments/`
- `operations/`
- `inputs/`
- `blueprints/`

Jenkins is only the trigger/orchestrator. Cloudify lifecycle logic remains common.

## Demo flow

1. Start Jenkins using `./reset-jenkins-e2e.sh`.
2. Run `cloudify-envops-git-polling` once to capture baseline.
3. Commit a deployment YAML change to create/reconcile environment.
4. Commit an operation YAML change to run install/configure/custom workflow.
5. Delete deployment YAML to remove the Cloudify environment.
