# Jenkins E2E Docker Compose for Cloudify Lifecycle

This package starts Jenkins in Docker and creates a ready-to-run pipeline job named `cloudify-lifecycle-e2e`.

The Jenkins job invokes the same script used by GitOps:

```bash
python3 scripts/cloudify_lifecycle.py --request <request-file>
```

## Run

```bash
cp .env.jenkins.example .env.jenkins
vi .env.jenkins
./reset-jenkins-e2e.sh
```

Open Jenkins:

```text
http://localhost:8080
```

Login using values from `.env.jenkins`:

```text
JENKINS_ADMIN_ID=admin
JENKINS_ADMIN_PASSWORD=admin123
```

Open the job:

```text
cloudify-lifecycle-e2e
```

Click:

```text
Build with Parameters
```

Select one request file and run.

## Configuration

Cloudify values are read from `.env.jenkins` and injected into the Jenkins container:

```text
CFY_MANAGER_URL=https://<cloudify-manager-ip-or-dns>
CFY_USERNAME=admin
CFY_PASSWORD=<password>
CFY_TENANT=default_tenant
CFY_API_VERSION=v3.1
CFY_INSECURE=true
DEFAULT_REQUEST_FILE=requests/jenkins/hello-dev-install.yaml
```

## Why this version uses .env.jenkins directly

For this local E2E package, the pipeline uses the Jenkins container environment directly. This avoids first-boot Jenkins credential-store/plugin timing issues and makes the demo one-command runnable.

For production Jenkins, use Jenkins Credentials and `withCredentials`. The lifecycle script itself remains exactly the same.
