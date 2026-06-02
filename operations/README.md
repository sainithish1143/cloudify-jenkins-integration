# Cloudify operation intent files

`operations/*.yaml` files execute a workflow on an existing Cloudify deployment.

Rules:

- Commit or modify `deployments/*.yaml` to create/reconcile a Cloudify environment.
- Commit or modify `operations/*.yaml` to execute a workflow.
- Commit only `inputs/*.yaml` to update data in Git; it does not execute a workflow by itself.
- Delete `deployments/*.yaml` to delete the Cloudify deployment based on the deployment deletion policy.

Do not use an `uninstall` operation file unless the target blueprint exposes an `uninstall` workflow. For this demo, deletion is performed by removing the deployment desired-state file:

```bash
git rm deployments/hello-dev.yaml
git commit -m "Remove hello dev Cloudify environment"
git push
```
