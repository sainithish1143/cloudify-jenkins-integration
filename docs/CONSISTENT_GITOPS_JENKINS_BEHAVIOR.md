# Consistent GitOps and Jenkins behavior

Both demos use the same Cloudify model and scripts:

- `deployments/*.yaml` defines which Cloudify environments should exist.
- `operations/*.yaml` defines which Cloudify workflow should be executed.
- `inputs/*.yaml` contains user/application data consumed by the blueprint/workflow.
- `scripts/gitops_reconcile.py` and `scripts/cloudify_lifecycle.py` are shared by GitOps and Jenkins.

## Important rule

Workflow execution is only triggered by operation intent files.
Deployment deletion is triggered by deleting the deployment desired-state file.

Do not use `operations/*uninstall*.yaml` unless the Cloudify blueprint exposes an `uninstall` workflow.
For this demo, deployment removal is done by deleting the deployment file:

```bash
git rm deployments/hello-dev.yaml
git commit -m "Remove hello dev Cloudify environment"
git push
```

This matches the GitOps demo behavior and avoids failures when a blueprint does not expose an `uninstall` workflow.

## Demo sequence

First run the Jenkins polling job once to capture the baseline. It should do no Cloudify action on the first run.

Then push commits one at a time:

```bash
# Create/reconcile environment
echo "# env $(date)" >> deployments/hello-dev.yaml
git add deployments/hello-dev.yaml
git commit -m "Jenkins create hello dev environment"
git push

# Execute install workflow
echo "# install $(date)" >> operations/hello-dev-install.yaml
git add operations/hello-dev-install.yaml
git commit -m "Jenkins run install workflow"
git push

# Execute configure workflow with updated input data
vi inputs/hello/dev.yaml
echo "# configure $(date)" >> operations/hello-dev-configure.yaml
git add inputs/hello/dev.yaml operations/hello-dev-configure.yaml
git commit -m "Jenkins run configure with updated inputs"
git push

# Delete Cloudify environment
git rm deployments/hello-dev.yaml
git commit -m "Jenkins remove hello dev environment"
git push
```
