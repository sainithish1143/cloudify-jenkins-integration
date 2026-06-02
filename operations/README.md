# Cloudify operation intent files

`operations/*.yaml` files execute a workflow on an existing Cloudify deployment.

Rules:

- Commit or modify `deployments/*.yaml` to create/reconcile a Cloudify environment.
- Commit or modify `operations/*.yaml` to execute a workflow.
- Commit only `inputs/*.yaml` to update data in Git; it does not execute a workflow by itself.
- Delete `deployments/*.yaml` to delete the Cloudify deployment based on the deployment deletion policy.

Do not use an `uninstall` operation file unless the target blueprint exposes an `uninstall` workflow. For this demo, deletion is performed by removing the deployment desired-state file:

```bash
git rm deployments/wr-demo-jenkins-hello.yaml
git commit -m "Remove wr-demo-jenkins-hello Cloudify environment"
git push
```

## Naming convention

This repo intentionally uses source-specific Cloudify IDs so the demo is clear in the Cloudify UI.

| Source | Blueprint ID | Deployment ID |
|---|---|---|
| JENKINS | `wr-demo-jenkins-hello-bp` | `wr-demo-jenkins-hello` |

Recommended production naming pattern:

```text
<org-or-product>-<automation-source>-<application>-<environment>
```

Examples:

```text
wr-demo-gitops-hello-dev
wr-demo-jenkins-hello
customer1-gitops-edgeapp-site001
customer1-jenkins-edgeapp-site001
```

The same scripts and YAML model are used by GitOps and Jenkins. Only the automation source prefix differs for demo clarity.
