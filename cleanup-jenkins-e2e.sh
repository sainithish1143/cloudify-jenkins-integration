#!/usr/bin/env bash
set -euo pipefail

docker compose -f docker-compose.jenkins.yml down --remove-orphans -v || true
docker rm -f cloudify-jenkins-e2e 2>/dev/null || true
docker volume ls -q | grep -E '(^|_)jenkins_home$' | xargs -r docker volume rm 2>/dev/null || true

echo "Jenkins E2E containers and volumes cleaned."
