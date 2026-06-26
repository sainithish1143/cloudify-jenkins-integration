#!/usr/bin/env python3
"""
Real Kubernetes Deployment via Conductor CI/CD Pipeline.
Deploys an nginx application to the cluster using the K8s API.
"""
import json
import os
import time
import requests
from cloudify import ctx
from cloudify.state import ctx_parameters as inputs

operation = ctx.operation.name.split('.')[-1]
props = ctx.node.properties

# K8s API config from service account
TOKEN = open('/var/run/secrets/kubernetes.io/serviceaccount/token').read()
CA = '/var/run/secrets/kubernetes.io/serviceaccount/ca.crt'
API = 'https://kubernetes.default.svc'
HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}
NAMESPACE = props['namespace']

ctx.logger.info("=" * 60)
ctx.logger.info(f"Conductor Helm Operation: {operation}")
ctx.logger.info(f"Release: {props['release_name']} | Namespace: {NAMESPACE}")
ctx.logger.info(f"Chart: {props['chart_repo']} v{props['chart_version']}")
ctx.logger.info(f"Registry: {props['image_registry']}")
ctx.logger.info("=" * 60)

DEPLOY_NAME = props['release_name']
REPLICAS = props['replica_count']


def k8s_request(method, path, data=None):
    url = f"{API}{path}"
    r = requests.request(method, url, headers=HEADERS, verify=CA, json=data)
    return r


if operation == 'create':
    ctx.logger.info(f"[DEPLOY] Creating namespace '{NAMESPACE}' if not exists...")
    ns_body = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE}}
    r = k8s_request("POST", "/api/v1/namespaces", ns_body)
    ctx.logger.info(f"[DEPLOY] Namespace: {r.status_code} ({'created' if r.status_code == 201 else 'exists'})")

    ctx.logger.info(f"[DEPLOY] Creating Deployment '{DEPLOY_NAME}' with {REPLICAS} replica(s)...")
    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": DEPLOY_NAME, "namespace": NAMESPACE},
        "spec": {
            "replicas": REPLICAS,
            "selector": {"matchLabels": {"app": DEPLOY_NAME}},
            "template": {
                "metadata": {"labels": {"app": DEPLOY_NAME}},
                "spec": {
                    "containers": [{
                        "name": "nginx",
                        "image": "nginx:1.27-alpine",
                        "ports": [{"containerPort": 80}]
                    }]
                }
            }
        }
    }
    r = k8s_request("POST", f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments", deployment)
    if r.status_code in (200, 201):
        ctx.logger.info(f"[DEPLOY] Deployment created successfully (HTTP {r.status_code})")
    else:
        ctx.logger.info(f"[DEPLOY] Response: {r.status_code} - {r.text[:200]}")
        if r.status_code == 409:
            ctx.logger.info("[DEPLOY] Deployment already exists, continuing.")
        else:
            raise Exception(f"Failed to create deployment: {r.status_code}")

    ctx.logger.info(f"[DEPLOY] Creating Service '{DEPLOY_NAME}-svc'...")
    svc = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": f"{DEPLOY_NAME}-svc", "namespace": NAMESPACE},
        "spec": {
            "selector": {"app": DEPLOY_NAME},
            "ports": [{"port": 80, "targetPort": 80}],
            "type": "ClusterIP"
        }
    }
    r = k8s_request("POST", f"/api/v1/namespaces/{NAMESPACE}/services", svc)
    ctx.logger.info(f"[DEPLOY] Service: {r.status_code} ({'created' if r.status_code == 201 else 'exists'})")

elif operation == 'configure':
    ctx.logger.info(f"[UPGRADE] Scaling '{DEPLOY_NAME}' to {REPLICAS} replicas...")
    patch = {"spec": {"replicas": REPLICAS}}
    r = k8s_request("PATCH", f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{DEPLOY_NAME}", patch)
    HEADERS['Content-Type'] = 'application/strategic-merge-patch+json'
    ctx.logger.info(f"[UPGRADE] Scale result: {r.status_code}")
    if inputs:
        ctx.logger.info(f"[UPGRADE] CI/CD provided inputs: {dict(inputs)}")

elif operation == 'start':
    ctx.logger.info(f"[VERIFY] Checking deployment '{DEPLOY_NAME}' status...")
    for i in range(12):
        r = k8s_request("GET", f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{DEPLOY_NAME}")
        if r.status_code == 200:
            status = r.json().get('status', {})
            ready = status.get('readyReplicas', 0)
            desired = status.get('replicas', REPLICAS)
            ctx.logger.info(f"[VERIFY] Pods ready: {ready}/{desired}")
            if ready >= desired:
                ctx.logger.info(f"[VERIFY] All pods are running. Deployment healthy.")
                break
        time.sleep(5)
    else:
        ctx.logger.info("[VERIFY] WARNING: Timeout waiting for pods, continuing anyway.")

elif operation == 'stop':
    ctx.logger.info(f"[SCALE-DOWN] Scaling '{DEPLOY_NAME}' to 0 replicas...")
    patch = {"spec": {"replicas": 0}}
    r = k8s_request("PATCH", f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{DEPLOY_NAME}", patch)
    ctx.logger.info(f"[SCALE-DOWN] Result: {r.status_code}")

elif operation == 'delete':
    ctx.logger.info(f"[DELETE] Removing deployment '{DEPLOY_NAME}'...")
    r = k8s_request("DELETE", f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{DEPLOY_NAME}")
    ctx.logger.info(f"[DELETE] Deployment: {r.status_code}")
    ctx.logger.info(f"[DELETE] Removing service '{DEPLOY_NAME}-svc'...")
    r = k8s_request("DELETE", f"/api/v1/namespaces/{NAMESPACE}/services/{DEPLOY_NAME}-svc")
    ctx.logger.info(f"[DELETE] Service: {r.status_code}")
    ctx.logger.info(f"[DELETE] Cleanup complete.")

ctx.logger.info("=" * 60)
ctx.logger.info(f"Operation '{operation}' completed.")
ctx.logger.info("=" * 60)
