# Production operation model

Both GitHub Actions GitOps and Jenkins use the same operating model:

| Git change | Cloudify action |
|---|---|
| Add/modify `deployments/*.yaml` | Create/reconcile Cloudify environment only |
| Add/modify `operations/*.yaml` | Execute the workflow named in the operation file |
| Add/modify `inputs/*.yaml` only | No Cloudify action by itself |
| Delete `deployments/*.yaml` | Delete/uninstall based on deletion policy |
| Delete `operations/*.yaml` | No Cloudify action |

## Deployment file

The deployment file is the source of truth for the Cloudify environment. It contains deployment ID, blueprint ID, blueprint path, input files, tenant, execution settings, and deletion policy.

## Operation file

The operation file is the workflow execution intent. It can execute any workflow available on the Cloudify deployment.

Examples:

```yaml
spec:
  deployment_ref: deployments/wr-demo-jenkins-hello.yaml
  workflow: install
```

```yaml
spec:
  deployment_ref: deployments/wr-demo-jenkins-hello.yaml
  workflow: execute_operation
  parameters:
    operation: cloudify.interfaces.lifecycle.configure
    node_ids:
      - hello_gitops_node
```

## Delete policy

- `manual`: deletion of deployment file fails; operator must handle cleanup explicitly.
- `delete_only`: delete Cloudify deployment using Cloudify API; safe for this demo because no uninstall workflow is required.
- `auto_uninstall_delete`: run configured uninstall workflow then delete deployment. Use only when the blueprint exposes that workflow.
