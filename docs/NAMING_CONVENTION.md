# Cloudify naming convention

Use predictable IDs so customers can clearly see which automation path created a Cloudify object.

## Pattern

```text
<org-or-demo>-<automation-source>-<application>-<environment>
```

## Current repo values

| Field | Value |
|---|---|
| Automation source | `jenkins` |
| Blueprint ID | `wr-demo-jenkins-hello-bp` |
| Deployment ID | `wr-demo-jenkins-hello` |
| Application name input | `jenkins-hello-service` |

## Why this matters

Cloudify UI primarily shows blueprint and deployment IDs. If GitOps and Jenkins both use `hello-gitops-bp` or `hello-gitops-dev`, the demo becomes confusing. With source-specific IDs, the UI clearly shows which integration created each object.

## Examples

```text
wr-demo-gitops-hello-bp
wr-demo-gitops-hello-dev
wr-demo-jenkins-hello-bp
wr-demo-jenkins-hello
```

## Production guidance

For real deployments, use names aligned to the customer environment:

```text
<customer>-<source>-<app>-<site-or-env>
```

Examples:

```text
telco1-gitops-o2adapter-dev
telco1-jenkins-o2adapter-dev
telco1-gitops-edgeapp-site001
telco1-jenkins-edgeapp-site001
```
