#!/usr/bin/env bash
set -euo pipefail

docker rm -f cloudify-jenkins-envops >/dev/null 2>&1 || true
docker compose -f docker-compose.jenkins.yml down -v --remove-orphans || true
