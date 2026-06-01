# Cloudify Jenkins Lifecycle Automation

This repository demonstrates and provides a production-ready Jenkins mechanism to invoke Cloudify blueprint lifecycle operations.

Jenkins can run manually with parameters or monitor this repo for changes:

```text
Manual Jenkins build / Git commit -> Jenkins Pipeline -> scripts/cloudify_lifecycle.py -> Cloudify Manager
```

## Layout

```text
Jenkinsfile.gitops                     # Jenkins Git-triggered pipeline
Jenkinsfile.e2e                        # Jenkins local/manual E2E pipeline
docker-compose.jenkins.yml             # One-command Jenkins deployment
jenkins/                               # Jenkins image, plugins, seed jobs
scripts/cloudify_lifecycle.py          # Common production-grade Cloudify runner
requests/                              # Lifecycle intent YAML files
blueprints/hello/                      # Example Cloudify blueprint
inputs/dev.yaml                        # Example deployment inputs
logs/                                  # Runtime logs, ignored by Git
```

## Production controls included

The runner includes request validation, Cloudify credential validation, blueprint/input path validation, retry with backoff, execution polling, timeout handling, idempotency controls, dry-run support, secret masking, per-run log file, JSON summary, and non-zero exit codes for Jenkins failures.

## Commit this repo

```bash
git init
git add .
git commit -m "Add Cloudify Jenkins lifecycle automation"
git branch -M main
git remote add origin https://github.com/<your-user-or-org>/cloudify-jenkins-lifecycle.git
git push -u origin main
```

## Configure Jenkins E2E

```bash
cp .env.jenkins.example .env.jenkins
vi .env.jenkins
```

Set at least:

```text
CFY_MANAGER_URL=http://<cloudify-manager-ip-or-dns>
CFY_USERNAME=admin
CFY_PASSWORD=<cloudify-password>
CFY_TENANT=default_tenant
CFY_API_VERSION=v3.1
CFY_INSECURE=true

ENABLE_JENKINS_GIT_JOB=true
JENKINS_GIT_REPO_URL=https://github.com/<your-user-or-org>/cloudify-jenkins-lifecycle.git
JENKINS_GIT_BRANCH=main
DEFAULT_REQUEST_FILE=requests/hello-dev-install.yaml
```

Start Jenkins:

```bash
./reset-jenkins-e2e.sh
```

Open:

```text
http://localhost:8080
```

Default login from `.env.jenkins`:

```text
admin / admin123
```

## Jenkins jobs created automatically

```text
cloudify-lifecycle-e2e              # Manual Build with Parameters
cloudify-lifecycle-gitops-polling   # Polls the configured Git repo
```

## Manual Jenkins run

Open:

```text
cloudify-lifecycle-e2e -> Build with Parameters
```

Select:

```text
requests/hello-dev-install.yaml
requests/hello-dev-update.yaml
requests/hello-dev-uninstall.yaml
```

## Jenkins Git-triggered run

Run the polling job once manually first:

```text
cloudify-lifecycle-gitops-polling -> Build Now
```

Then push a request change:

```bash
cp requests/hello-dev-install.yaml requests/my-app-dev-install.yaml
vi requests/my-app-dev-install.yaml
git add requests/my-app-dev-install.yaml
git commit -m "Trigger Cloudify lifecycle from Jenkins"
git push
```

Jenkins will detect the repo change and run:

```bash
python3 scripts/cloudify_lifecycle.py --request <changed-request-file>
```

## Local test without Jenkins

```bash
cp .env.example .env
vi .env
./run-compose.sh requests/hello-dev-install.yaml
```
