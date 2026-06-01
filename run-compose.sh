#!/usr/bin/env bash
set -euo pipefail

REQUEST_FILE="${1:-requests/hello-dev-install.yaml}"

if [ ! -f .env ]; then
  echo "Missing .env. Creating from .env.example. Please update Cloudify URL/password and rerun."
  cp .env.example .env
  exit 1
fi

CFY_REQUEST_FILE="$REQUEST_FILE" docker compose up --build --abort-on-container-exit --exit-code-from cloudify-lifecycle cloudify-lifecycle
