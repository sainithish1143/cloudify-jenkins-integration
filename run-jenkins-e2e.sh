#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env.jenkins ]; then
  cp .env.jenkins.example .env.jenkins
  echo "Created .env.jenkins from example. Please edit Cloudify/Jenkins values and rerun."
  exit 1
fi

docker compose -f docker-compose.jenkins.yml up -d --build

echo "Jenkins is starting at: http://localhost:8080"
echo "Jobs: cloudify-envops-manual, cloudify-envops-git-polling"
