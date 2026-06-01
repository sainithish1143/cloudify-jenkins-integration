#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker-compose.jenkins.yml"
CONTAINER_NAME="cloudify-jenkins-e2e"

if [ ! -f ".env.jenkins" ]; then
  echo "ERROR: .env.jenkins not found. Run: cp .env.jenkins.example .env.jenkins and update Cloudify values."
  exit 1
fi

echo "Stopping Jenkins E2E stack and removing compose volume..."
docker compose -f "${COMPOSE_FILE}" down --remove-orphans -v || true

echo "Removing old Jenkins container by fixed name, if it still exists..."
docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

echo "Removing any stale Jenkins home volumes for this project, if present..."
docker volume ls -q | grep -E '(^|_)jenkins_home$' | xargs -r docker volume rm 2>/dev/null || true

echo "Starting fresh Jenkins E2E stack..."
docker compose -f "${COMPOSE_FILE}" up -d --build --force-recreate

echo ""
echo "Jenkins is starting at: http://localhost:8080"
echo "Login with JENKINS_ADMIN_USER / JENKINS_ADMIN_PASSWORD from .env.jenkins"
echo "Job: cloudify-lifecycle-e2e"
echo "Expected left menu action: Build with Parameters"
