#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env.jenkins ]; then
  echo "Creating .env.jenkins from .env.jenkins.example"
  cp .env.jenkins.example .env.jenkins
  echo "Please edit .env.jenkins with your Cloudify Manager details, then run this again."
  exit 1
fi

docker compose -f docker-compose.jenkins.yml up -d --build

echo ""
echo "Jenkins is starting at: http://localhost:8080"
echo "Default user/password are from .env.jenkins"
echo "Open job: cloudify-lifecycle-e2e"
echo ""
echo "To view logs: docker logs -f cloudify-jenkins-e2e"
