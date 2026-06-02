# Commit-Based Desired-State GitOps Procedure

## Production pattern

```text
deployments/<deployment-id>.yaml
```

The deployment desired-state file is the source of truth.

```text
File added    -> install
File modified -> update
File deleted  -> uninstall
```

## Example deployment file

```yaml
apiVersion: cloudify.windriver.com/v1
kind: CloudifyDeployment
metadata:
  name: app1-dev
spec:
  enabled: true
  manager:
    tenant: default_tenant
  blueprint:
    id: app1-bp
    source: blueprints/hello
    application_file: blueprint.yaml
  deployment:
    id: app1-dev
    inputs:
      - inputs/hello/dev.yaml
  lifecycle:
    install:
      workflow: install
      wait: true
      timeout_sec: 3600
    update:
      workflow: update
      wait: true
      timeout_sec: 3600
    uninstall:
      workflow: uninstall
      wait: true
      timeout_sec: 3600
      delete_deployment: true
      delete_blueprint: false
```

## Demo sequence

1. Add file under `deployments/` to install.
2. Edit the same file to update.
3. Delete the same file to uninstall.

## User inputs in execution logs

Change `inputs/hello/dev.yaml` values and run update by modifying the deployment file or manually triggering update.
The blueprint lifecycle script prints the values in Cloudify execution logs.
