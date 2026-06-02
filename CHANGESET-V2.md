# Verified production final v2

This package was regenerated after review to avoid confusion with older downloads.

Confirmed contents:
- Source-specific naming is applied.
- Deployment IDs do not use `-dev` or `_dev` suffix.
- Multiple deployment examples are included under `examples/multi-deployment/`.
- Optional uninstall workflow samples are included as `.yaml.sample` so they do not execute accidentally.
- GitOps and Jenkins packages use the same common script names and same execution model:
  - `scripts/cloudify_lifecycle.py`
  - `scripts/gitops_reconcile.py`
  - `scripts/manual_lifecycle_from_deployment.py`
- Operation files can pass workflow parameters using `spec.parameters`.
- Deployment file deletion remains the standard desired-state cleanup path.

Naming convention:
- GitOps: `wr-demo-gitops-*`
- Jenkins: `wr-demo-jenkins-*`

Generated package root: `cloudify-jenkins-integration`
