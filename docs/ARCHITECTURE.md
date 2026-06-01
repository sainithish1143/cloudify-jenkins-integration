# Architecture

```text
                          +-----------------------------+
                          |     scripts/cloudify_       |
                          |     lifecycle.py            |
                          |  Common lifecycle engine    |
                          +--------------+--------------+
                                         |
                                         v
                                Cloudify Manager

Local Docker Compose  ---> requests/gitops/*  ----+
GitHub Actions GitOps ---> requests/gitops/*  ----+---- same script
Jenkins manual        ---> requests/jenkins/* ----+
Jenkins Git polling   ---> requests/jenkins/* ----+
```

## Why two request folders?

One repository can safely demonstrate and operate both GitHub Actions GitOps and Jenkins Git-triggered automation when the trigger folders are separated:

- GitHub Actions watches `requests/gitops/**`.
- Jenkins watches `requests/jenkins/**`.

This prevents one commit from triggering the same Cloudify deployment twice.

## Common lifecycle engine

The common script handles:

- authentication
- blueprint upload
- deployment create/reuse
- workflow execution
- uninstall/delete
- retries
- validation
- timeouts
- structured logs and audit summary

## Request as intent

A request YAML represents the desired lifecycle action. Example:

```yaml
operation: install
blueprint_id: hello-gitops-bp
deployment_id: hello-gitops-dev
blueprint_dir: blueprints/hello
inputs_files:
  - inputs/dev.yaml
workflow: install
```
