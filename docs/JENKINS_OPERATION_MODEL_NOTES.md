# Jenkins EnvOps operation model notes

The Jenkins integration uses the same Cloudify EnvOps model as GitOps:

- `deployments/*.yaml` commits create or reconcile Cloudify environments/deployments.
- `operations/*.yaml` commits execute Cloudify workflows.
- `inputs/*.yaml` commits only change data; pair them with an operation commit to execute a workflow.

## Important first-run behavior

When a Jenkins polling job runs for the first time against a repository that already contains deployment and operation files, Jenkins may see all files as new depending on its baseline. For a clean demo:

1. Start Jenkins and run `cloudify-envops-git-polling` once to establish baseline, or
2. Keep operation files unchanged until you want to trigger them, or
3. Trigger with manual Jenkins job first.

## Idempotency

The lifecycle runner treats an existing blueprint as a successful no-op. This avoids failures such as:

`409 blueprint already exists`

For major blueprint changes in production, use a new `blueprint_id` version or implement a controlled update/migration workflow.
