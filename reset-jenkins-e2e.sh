#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env.jenkins ]; then
  cp .env.jenkins.example .env.jenkins
  echo "Created .env.jenkins from example. Please edit Cloudify/Jenkins values and rerun."
  exit 1
fi

echo "Stopping and removing old Jenkins EnvOps stack..."
docker rm -f cloudify-jenkins-envops >/dev/null 2>&1 || true
docker compose -f docker-compose.jenkins.yml down -v --remove-orphans || true

echo "Starting fresh Jenkins EnvOps stack..."
docker compose -f docker-compose.jenkins.yml up -d --build

echo
echo "Jenkins is starting at: http://localhost:8080"
echo "Login with JENKINS_ADMIN_ID / JENKINS_ADMIN_PASSWORD from .env.jenkins"
echo "Jobs: cloudify-envops-manual, cloudify-envops-git-polling"
