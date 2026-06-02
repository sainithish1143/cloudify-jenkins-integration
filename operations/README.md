# Operation intents

Operation files execute workflows on an existing Cloudify deployment.

For this demo, use:

- `hello-dev-install.yaml` to execute the `install` workflow.
- `hello-dev-configure.yaml` to execute `execute_operation` and print Git-provided input values in Cloudify logs.

Do **not** use an operation file to delete the deployment unless the target blueprint explicitly exposes that workflow.
To remove the Cloudify environment consistently in both GitOps and Jenkins demos, delete the deployment desired-state file:

```bash
git rm deployments/hello-dev.yaml
git commit -m "Remove hello dev Cloudify environment"
git push
```
