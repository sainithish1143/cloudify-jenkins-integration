# Production-Grade Design Notes

## Trigger separation

This repository supports both Jenkins and GitOps from the same codebase without duplicate execution:

| Trigger | Watches | Runs |
|---|---|---|
| GitHub Actions GitOps | `requests/gitops/**` | `scripts/cloudify_lifecycle.py` |
| Jenkins Git polling | `requests/jenkins/**` | `scripts/cloudify_lifecycle.py` |
| Jenkins manual | selected parameter | `scripts/cloudify_lifecycle.py` |
| Local Compose | selected argument | `scripts/cloudify_lifecycle.py` |

## Request YAML contract

Each request file represents lifecycle intent:

```yaml
operation: install
manager_url: ${CFY_MANAGER_URL}
username: ${CFY_USERNAME}
password: ${CFY_PASSWORD}
tenant: ${CFY_TENANT:-default_tenant}
api_version: ${CFY_API_VERSION:-v3.1}
insecure: true
blueprint_id: hello-gitops-bp
deployment_id: hello-gitops-dev
blueprint_dir: blueprints/hello
application_file: blueprint.yaml
inputs_files:
  - inputs/dev.yaml
workflow: install
wait: true
request_timeout_sec: 60
execution_timeout_sec: 3600
poll_interval_sec: 10
retry_count: 5
retry_backoff_sec: 2
log_level: INFO
log_dir: logs
```

## Idempotency controls

Optional fields:

```yaml
if_blueprint_exists: upload   # upload | skip | fail
if_deployment_exists: reuse   # reuse | skip | fail | recreate
ignore_missing: true
force_delete: false
```

Recommended defaults:

- `if_blueprint_exists: upload` keeps the blueprint content current.
- `if_deployment_exists: reuse` avoids unnecessary deployment recreation.
- `delete_deployment: true` only for uninstall/delete flows.

## Logging and audit

Every run writes:

```text
logs/cloudify-lifecycle-<run_id>.log
logs/cloudify-lifecycle-<run_id>.summary.json
```

The summary is suitable for CI archival and later troubleshooting.

## Failure handling

The script returns non-zero for:

- missing Cloudify credentials
- invalid request YAML
- missing blueprint or inputs files
- authentication failure
- API failure after retries
- workflow failed/cancelled state
- workflow timeout

## Concurrency

GitHub Actions uses workflow concurrency:

```yaml
concurrency:
  group: cloudify-gitops-${{ github.ref }}
  cancel-in-progress: false
```

Jenkins uses:

```groovy
disableConcurrentBuilds()
```

This prevents accidental concurrent lifecycle runs from the same automation path.
