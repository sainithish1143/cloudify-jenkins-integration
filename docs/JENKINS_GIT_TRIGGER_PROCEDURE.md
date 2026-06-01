# Jenkins Git Trigger Procedure

## Goal

Jenkins should watch the same repo, detect relevant changes, and run the same Cloudify lifecycle script.

## Folder used by Jenkins Git trigger

Jenkins watches only:

```text
requests/jenkins/**
```

It does not run request files from:

```text
requests/gitops/**
```

This prevents duplicate execution with GitHub Actions.

## Configure `.env.jenkins`

```bash
cp .env.jenkins.example .env.jenkins
vi .env.jenkins
```

Required values:

```text
CFY_MANAGER_URL=http://<cloudify-manager-ip>
CFY_USERNAME=admin
CFY_PASSWORD=<password>
CFY_TENANT=default_tenant
CFY_API_VERSION=v3.1
CFY_INSECURE=true

ENABLE_JENKINS_GIT_JOB=true
JENKINS_GIT_REPO_URL=https://github.com/shashikanth-vh/gitops.git
JENKINS_GIT_BRANCH=main
JENKINS_POLL_SCHEDULE=H/2 * * * *
DEFAULT_REQUEST_FILE=requests/jenkins/hello-dev-install.yaml
```

## Start Jenkins

```bash
./reset-jenkins-e2e.sh
```

Open:

```text
http://localhost:8080
```

Jobs created:

```text
cloudify-lifecycle-e2e
cloudify-lifecycle-gitops-polling
```

## Manual Jenkins job

Use:

```text
cloudify-lifecycle-e2e -> Build with Parameters
```

Select:

```text
requests/jenkins/hello-dev-install.yaml
```

## Git-triggered Jenkins job

Run once manually first:

```text
cloudify-lifecycle-gitops-polling -> Build Now
```

Then commit a Jenkins request change:

```bash
vi requests/jenkins/hello-dev-install.yaml
git add requests/jenkins/hello-dev-install.yaml
git commit -m "Trigger Jenkins Cloudify install"
git push
```

Jenkins will poll the repo, detect the changed request under `requests/jenkins/**`, and run:

```bash
python3 scripts/cloudify_lifecycle.py --request requests/jenkins/hello-dev-install.yaml
```

## Logs

Jenkins archives:

```text
logs/**
```

Each run includes a `.log` file and `.summary.json` audit file.
