# Run Cloudify lifecycle using Docker Compose

This wrapper lets you run the same `scripts/cloudify_lifecycle.py` used by Jenkins and GitOps, but from Docker Compose.

## 1. Configure Cloudify connection

```bash
cp .env.example .env
vi .env
```

Update:

```bash
CFY_MANAGER_URL=https://<cloudify-manager-ip-or-dns>
CFY_USERNAME=admin
CFY_PASSWORD=<password>
CFY_TENANT=default_tenant
CFY_INSECURE=true
```

## 2. Run install

```bash
docker compose up --build --abort-on-container-exit --exit-code-from cloudify-lifecycle cloudify-lifecycle
```

Or:

```bash
./run-compose.sh requests/gitops/hello-dev-install.yaml
```

## 3. Run update

```bash
./run-compose.sh requests/gitops/hello-dev-update.yaml
```

## 4. Run uninstall

```bash
./run-compose.sh requests/gitops/hello-dev-uninstall.yaml
```

## 5. Use compose profiles

```bash
docker compose --profile install up --build --abort-on-container-exit --exit-code-from cloudify-install cloudify-install

docker compose --profile update up --build --abort-on-container-exit --exit-code-from cloudify-update cloudify-update

docker compose --profile uninstall up --build --abort-on-container-exit --exit-code-from cloudify-uninstall cloudify-uninstall
```

## Important

This Docker Compose file runs the lifecycle client. It does not start Cloudify Manager itself. `CFY_MANAGER_URL` must point to a reachable Cloudify Manager.
