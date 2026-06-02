#!/usr/bin/env bash
set -euo pipefail

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

ACTION="${1:-create-environment}"
DEPLOYMENT_FILE="${2:-deployments/wr-demo-jenkins-hello-dev.yaml}"
WORKFLOW="${3:-install}"

case "$ACTION" in
  create-environment)
    python3 scripts/manual_lifecycle_from_deployment.py --deployment "$DEPLOYMENT_FILE" --action create-environment
    ;;
  execute-workflow)
    python3 scripts/manual_lifecycle_from_deployment.py --deployment "$DEPLOYMENT_FILE" --action execute-workflow --workflow "$WORKFLOW"
    ;;
  configure)
    python3 scripts/manual_lifecycle_from_deployment.py --deployment "$DEPLOYMENT_FILE" --action execute-workflow --workflow execute_operation --parameters-file workflow-params/execute-configure.yaml --inject-inputs-as-operation-kwargs
    ;;
  uninstall)
    python3 scripts/manual_lifecycle_from_deployment.py --deployment "$DEPLOYMENT_FILE" --action uninstall --workflow uninstall
    ;;
  delete-environment)
    python3 scripts/manual_lifecycle_from_deployment.py --deployment "$DEPLOYMENT_FILE" --action delete-environment
    ;;
  *)
    echo "Usage: $0 {create-environment|execute-workflow|uninstall|delete-environment} [deployment-file] [workflow]"
    exit 1
    ;;
esac
