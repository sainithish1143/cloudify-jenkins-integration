# Environment + Operation Intent Model

Deployment files define Cloudify environments.
Operation files define Cloudify workflow executions.

This allows different blueprints, different inputs, different deployment IDs, and any workflow name/parameters per deployment.

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
