# Multiple deployments with the same blueprint

This package supports multiple Cloudify deployments using the same blueprint and different input files.

## Model

```text
blueprints/hello/blueprint.yaml      # shared blueprint
inputs/hello/app1-dev.yaml           # App1-specific values
inputs/hello/app2-dev.yaml           # App2-specific values
deployments/app1-dev.yaml            # Cloudify deployment app1-dev
deployments/app2-dev.yaml            # Cloudify deployment app2-dev
operations/app1-dev-install.yaml     # workflow intent for app1-dev
operations/app2-dev-install.yaml     # workflow intent for app2-dev
```

Each deployment file has its own `spec.deployment.id` and input file list. The blueprint may be shared:

```yaml
spec:
  blueprint:
    id: hello-shared-bp
    source: blueprints/hello
  deployment:
    id: app1-dev
    inputs:
      - inputs/hello/app1-dev.yaml
```

```yaml
spec:
  blueprint:
    id: hello-shared-bp
    source: blueprints/hello
  deployment:
    id: app2-dev
    inputs:
      - inputs/hello/app2-dev.yaml
```

## How to try it

Copy the examples into the active folders:

```bash
cp examples/multi-deployment/inputs/hello/app1-dev.yaml inputs/hello/app1-dev.yaml
cp examples/multi-deployment/deployments/app1-dev.yaml deployments/app1-dev.yaml
cp examples/multi-deployment/operations/app1-dev-install.yaml operations/app1-dev-install.yaml

git add inputs/hello/app1-dev.yaml deployments/app1-dev.yaml operations/app1-dev-install.yaml
git commit -m "Create app1 dev environment and run install"
git push
```

Then for app2:

```bash
cp examples/multi-deployment/inputs/hello/app2-dev.yaml inputs/hello/app2-dev.yaml
cp examples/multi-deployment/deployments/app2-dev.yaml deployments/app2-dev.yaml
cp examples/multi-deployment/operations/app2-dev-install.yaml operations/app2-dev-install.yaml

git add inputs/hello/app2-dev.yaml deployments/app2-dev.yaml operations/app2-dev-install.yaml
git commit -m "Create app2 dev environment and run install"
git push
```

## Production guidance

A deployment file is the identity and desired state of one Cloudify deployment. An operation file is a workflow intent against that deployment. Jenkins and GitOps should both use this same model.
