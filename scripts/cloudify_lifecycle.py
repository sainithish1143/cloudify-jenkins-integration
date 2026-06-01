#!/usr/bin/env python3
"""
Production-ready reusable Cloudify lifecycle runner.

One implementation used by:
  - Local Docker Compose
  - Jenkins manual job
  - Jenkins Git-triggered job
  - GitHub Actions GitOps workflow

Design goals:
  - Same request YAML contract across all callers
  - Strong validation before touching Cloudify
  - Idempotent/resource-aware behavior where possible
  - Structured logging and audit summary output
  - Retries for transient API/network failures
  - Clear non-zero exit code on failure for CI/CD systems
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import sys
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import requests
import yaml


class CloudifyLifecycleError(RuntimeError):
    pass


SENSITIVE_KEYS = {"password", "token", "secret", "authorization", "authentication-token"}
TERMINAL_SUCCESS = {"terminated"}
TERMINAL_FAILURE = {"failed", "cancelled", "cancelling", "force_cancelling"}
SUPPORTED_OPERATIONS = {"install", "update", "execute", "uninstall", "delete"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mask_secret(value: Any) -> str:
    if value is None:
        return ""
    value = str(value)
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]


def sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        clean = {}
        for key, value in obj.items():
            if any(s in str(key).lower() for s in SENSITIVE_KEYS):
                clean[key] = mask_secret(value)
            else:
                clean[key] = sanitize(value)
        return clean
    if isinstance(obj, list):
        return [sanitize(item) for item in obj]
    return obj


def env_expand(value: Any) -> Any:
    """Expand ${VAR} and ${VAR:-default} inside YAML string values."""
    if isinstance(value, str):
        pattern = re.compile(r"\$\{([^}:]+)(:-([^}]*))?\}")

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            default = match.group(3)
            return os.getenv(name, default or "")

        return pattern.sub(replace, value)
    if isinstance(value, list):
        return [env_expand(item) for item in value]
    if isinstance(value, dict):
        return {key: env_expand(val) for key, val in value.items()}
    return value


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    result.update({k: v for k, v in override.items() if v is not None})
    return result


def repo_root_from_request(request_path: Optional[str]) -> Path:
    if request_path:
        p = Path(request_path).resolve()
        cur = p.parent
        while cur != cur.parent:
            if (cur / "scripts" / "cloudify_lifecycle.py").exists():
                return cur
            cur = cur.parent
    return Path.cwd().resolve()


def load_yaml(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise CloudifyLifecycleError(f"YAML file not found: {path}")
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise CloudifyLifecycleError(f"YAML top-level must be a mapping: {path}")
    return env_expand(data)


@dataclass
class Config:
    manager_url: str
    username: str
    password: str
    tenant: str
    api_version: str = "v3.1"
    insecure: bool = False
    request_timeout_sec: int = 60
    execution_timeout_sec: int = 3600
    poll_interval_sec: int = 10
    retry_count: int = 5
    retry_backoff_sec: int = 2

    def api_url(self, path: str) -> str:
        version = self.api_version.strip("/")
        if version.startswith("api/"):
            version = version[4:]
        return f"{self.manager_url.rstrip('/')}/api/{version}/{path.lstrip('/')}"


class Audit:
    def __init__(self, run_id: str, request_file: str, log_dir: Path) -> None:
        self.run_id = run_id
        self.request_file = request_file
        self.log_dir = log_dir
        self.started_at = utc_now()
        self.data: Dict[str, Any] = {
            "run_id": run_id,
            "request_file": request_file,
            "started_at": self.started_at,
            "status": "running",
            "events": [],
        }

    def event(self, name: str, **kwargs: Any) -> None:
        self.data["events"].append({"time": utc_now(), "name": name, **sanitize(kwargs)})

    def finish(self, status: str, **kwargs: Any) -> Path:
        self.data["status"] = status
        self.data["finished_at"] = utc_now()
        self.data.update(sanitize(kwargs))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self.log_dir / f"cloudify-lifecycle-{self.run_id}.summary.json"
        path.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
        return path


def setup_logging(values: Dict[str, Any], run_id: str, repo_root: Path) -> Path:
    log_level = str(values.get("log_level") or os.getenv("LOG_LEVEL") or "INFO").upper()
    log_dir = Path(values.get("log_dir") or os.getenv("LOG_DIR") or "logs")
    if not log_dir.is_absolute():
        log_dir = repo_root / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"cloudify-lifecycle-{run_id}.log"

    handlers = [logging.StreamHandler(sys.stdout), logging.FileHandler(log_file, encoding="utf-8")]
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)sZ %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=handlers,
        force=True,
    )
    logging.info("Cloudify lifecycle run_id=%s", run_id)
    logging.info("Log file: %s", log_file)
    return log_dir


class CloudifyClient:
    def __init__(self, cfg: Config, audit: Audit) -> None:
        self.cfg = cfg
        self.audit = audit
        self.token: Optional[str] = None

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        json_body: Optional[Any] = None,
        data_body: Optional[Any] = None,
        content_type: Optional[str] = None,
        retries: Optional[int] = None,
    ) -> Tuple[int, str, Dict[str, Any]]:
        retries = retries if retries is not None else self.cfg.retry_count
        url = self.cfg.api_url(path)
        merged_headers = dict(headers or {})
        merged_headers.setdefault("Tenant", self.cfg.tenant)
        if self.token:
            merged_headers.setdefault("Authentication-Token", self.token)
        if content_type:
            merged_headers["Content-Type"] = content_type

        last_error: Optional[BaseException] = None
        for attempt in range(1, retries + 1):
            try:
                logging.debug("HTTP %s %s attempt=%s", method, path, attempt)
                response = requests.request(
                    method=method,
                    url=url,
                    headers=merged_headers,
                    params=params,
                    json=json_body,
                    data=data_body,
                    verify=not self.cfg.insecure,
                    timeout=self.cfg.request_timeout_sec,
                )
                text = response.text or ""
                try:
                    payload = response.json() if text.strip() else {}
                except ValueError:
                    payload = {}

                if response.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                    sleep_sec = self.cfg.retry_backoff_sec * attempt
                    logging.warning("HTTP %s for %s %s; retrying in %ss (%s/%s)", response.status_code, method, path, sleep_sec, attempt, retries)
                    time.sleep(sleep_sec)
                    continue
                return response.status_code, text, payload
            except requests.RequestException as exc:
                last_error = exc
                if attempt < retries:
                    sleep_sec = self.cfg.retry_backoff_sec * attempt
                    logging.warning("Request error for %s %s: %s; retrying in %ss (%s/%s)", method, path, exc, sleep_sec, attempt, retries)
                    time.sleep(sleep_sec)
                    continue
        raise CloudifyLifecycleError(f"Request failed after retries: {method} {path}: {last_error}")

    def authenticate(self) -> None:
        basic = base64.b64encode(f"{self.cfg.username}:{self.cfg.password}".encode()).decode()
        body = {"username": self.cfg.username, "password": self.cfg.password, "tenant_name": self.cfg.tenant}
        status, text, payload = self.request("POST", "tokens", headers={"Authorization": f"Basic {basic}"}, json_body=body, content_type="application/json")
        if status >= 400:
            raise CloudifyLifecycleError(f"Cloudify authentication failed HTTP {status}: {text}")
        token = payload.get("value")
        if not token:
            raise CloudifyLifecycleError(f"Cloudify token missing in response: {text}")
        self.token = token
        logging.info("Authenticated to Cloudify Manager tenant=%s url=%s", self.cfg.tenant, self.cfg.manager_url)
        self.audit.event("authenticated", tenant=self.cfg.tenant, manager_url=self.cfg.manager_url)

    def exists(self, resource_path: str) -> bool:
        status, text, _ = self.request("GET", resource_path)
        if status == 404:
            return False
        if status >= 400:
            raise CloudifyLifecycleError(f"Failed to check {resource_path} HTTP {status}: {text}")
        return True

    def upload_blueprint(self, blueprint_id: str, blueprint_dir: str, application_file: str, if_exists: str = "upload") -> None:
        exists = self.exists(f"blueprints/{blueprint_id}")
        if exists and if_exists == "skip":
            logging.info("Blueprint '%s' already exists; skipping upload", blueprint_id)
            self.audit.event("blueprint_upload_skipped", blueprint_id=blueprint_id)
            return
        if exists and if_exists == "fail":
            raise CloudifyLifecycleError(f"Blueprint already exists and if_blueprint_exists=fail: {blueprint_id}")

        archive_path = build_blueprint_archive(blueprint_id, blueprint_dir)
        params = {"application_file": application_file}
        logging.info("Uploading blueprint '%s' from %s", blueprint_id, archive_path)
        with open(archive_path, "rb") as handle:
            status, text, _ = self.request("PUT", f"blueprints/{blueprint_id}", params=params, data_body=handle, content_type="application/zip")
        try:
            archive_path.unlink(missing_ok=True)
        except OSError:
            pass
        if status >= 400:
            raise CloudifyLifecycleError(f"Blueprint upload failed HTTP {status}: {text}")
        self.audit.event("blueprint_uploaded", blueprint_id=blueprint_id)

    def create_deployment(self, deployment_id: str, blueprint_id: str, inputs: Dict[str, Any], if_exists: str = "reuse") -> bool:
        exists = self.exists(f"deployments/{deployment_id}")
        if exists:
            if if_exists == "reuse":
                logging.info("Deployment '%s' already exists; reusing it", deployment_id)
                self.audit.event("deployment_reused", deployment_id=deployment_id)
                return False
            if if_exists == "skip":
                logging.info("Deployment '%s' already exists; skipping create", deployment_id)
                self.audit.event("deployment_create_skipped", deployment_id=deployment_id)
                return False
            if if_exists == "fail":
                raise CloudifyLifecycleError(f"Deployment already exists and if_deployment_exists=fail: {deployment_id}")
            if if_exists != "recreate":
                raise CloudifyLifecycleError(f"Unsupported if_deployment_exists value: {if_exists}")
            self.delete_deployment(deployment_id, force=True)

        logging.info("Creating deployment '%s' from blueprint '%s'", deployment_id, blueprint_id)
        status, text, _ = self.request("PUT", f"deployments/{deployment_id}", json_body={"blueprint_id": blueprint_id, "inputs": inputs}, content_type="application/json")
        if status >= 400:
            raise CloudifyLifecycleError(f"Deployment create failed HTTP {status}: {text}")
        self.audit.event("deployment_created", deployment_id=deployment_id, blueprint_id=blueprint_id)
        return True

    def start_execution(self, deployment_id: str, workflow: str, parameters: Optional[Dict[str, Any]] = None, allow_custom_parameters: bool = True) -> str:
        body: Dict[str, Any] = {"deployment_id": deployment_id, "workflow_id": workflow, "allow_custom_parameters": allow_custom_parameters}
        if parameters:
            body["parameters"] = parameters
        logging.info("Starting workflow '%s' on deployment '%s'", workflow, deployment_id)
        status, text, payload = self.request("POST", "executions", json_body=body, content_type="application/json")
        if status >= 400:
            raise CloudifyLifecycleError(f"Execution start failed HTTP {status}: {text}")
        execution_id = payload.get("id")
        if not execution_id:
            raise CloudifyLifecycleError(f"Execution id missing in response: {text}")
        self.audit.event("execution_started", deployment_id=deployment_id, workflow=workflow, execution_id=execution_id)
        return execution_id

    def wait_for_execution(self, execution_id: str) -> None:
        deadline = time.time() + self.cfg.execution_timeout_sec
        last_status = None
        while True:
            status, text, payload = self.request("GET", f"executions/{execution_id}")
            if status >= 400:
                raise CloudifyLifecycleError(f"Execution read failed HTTP {status}: {text}")
            execution_status = payload.get("status", "unknown")
            if execution_status != last_status:
                logging.info("Execution %s status=%s", execution_id, execution_status)
                self.audit.event("execution_status", execution_id=execution_id, status=execution_status)
                last_status = execution_status
            else:
                logging.debug("Execution %s status=%s", execution_id, execution_status)
            if execution_status in TERMINAL_SUCCESS:
                return
            if execution_status in TERMINAL_FAILURE:
                error = payload.get("error") or text
                raise CloudifyLifecycleError(f"Execution {execution_id} ended as {execution_status}: {error}")
            if time.time() > deadline:
                raise CloudifyLifecycleError(f"Timed out waiting for execution {execution_id}; last status={execution_status}")
            time.sleep(self.cfg.poll_interval_sec)

    def delete_deployment(self, deployment_id: str, *, force: bool = False, ignore_missing: bool = True) -> None:
        if ignore_missing and not self.exists(f"deployments/{deployment_id}"):
            logging.info("Deployment '%s' does not exist; skipping delete", deployment_id)
            self.audit.event("deployment_delete_skipped", deployment_id=deployment_id)
            return
        params = {"force": "true"} if force else None
        logging.info("Deleting deployment '%s' force=%s", deployment_id, force)
        status, text, _ = self.request("DELETE", f"deployments/{deployment_id}", params=params)
        if status == 404 and ignore_missing:
            return
        if status not in {200, 204} and status >= 400:
            raise CloudifyLifecycleError(f"Deployment delete failed HTTP {status}: {text}")
        self.audit.event("deployment_deleted", deployment_id=deployment_id)

    def delete_blueprint(self, blueprint_id: str, *, force: bool = False, ignore_missing: bool = True) -> None:
        if ignore_missing and not self.exists(f"blueprints/{blueprint_id}"):
            logging.info("Blueprint '%s' does not exist; skipping delete", blueprint_id)
            self.audit.event("blueprint_delete_skipped", blueprint_id=blueprint_id)
            return
        params = {"force": "true"} if force else None
        logging.info("Deleting blueprint '%s' force=%s", blueprint_id, force)
        status, text, _ = self.request("DELETE", f"blueprints/{blueprint_id}", params=params)
        if status == 404 and ignore_missing:
            return
        if status not in {200, 204} and status >= 400:
            raise CloudifyLifecycleError(f"Blueprint delete failed HTTP {status}: {text}")
        self.audit.event("blueprint_deleted", blueprint_id=blueprint_id)


def resolve_path(repo_root: Path, path: str) -> str:
    p = Path(path)
    return str(p if p.is_absolute() else repo_root / p)


def build_blueprint_archive(blueprint_id: str, blueprint_dir: str) -> Path:
    src = Path(blueprint_dir)
    if not src.is_dir():
        raise CloudifyLifecycleError(f"Blueprint directory not found: {blueprint_dir}")
    application_candidates = list(src.glob("*.yaml")) + list(src.glob("*.yml"))
    if not application_candidates:
        raise CloudifyLifecycleError(f"No blueprint YAML found under: {blueprint_dir}")
    archive = Path("/tmp") / f"{blueprint_id}-{uuid.uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in src.rglob("*"):
            if file_path.is_file():
                relative = file_path.relative_to(src)
                zip_file.write(file_path, Path(blueprint_id) / relative)
    return archive


def load_inputs(files: Iterable[str], repo_root: Path) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for item in files:
        merged = merge_dicts(merged, load_yaml(resolve_path(repo_root, item)))
    return merged


def build_config(values: Dict[str, Any]) -> Config:
    manager_url = values.get("manager_url") or os.getenv("CFY_MANAGER_URL")
    username = values.get("username") or os.getenv("CFY_USERNAME")
    password = values.get("password") or os.getenv("CFY_PASSWORD")
    tenant = values.get("tenant") or os.getenv("CFY_TENANT") or "default_tenant"
    missing = [name for name, val in {"manager_url": manager_url, "username": username, "password": password}.items() if not val]
    if missing:
        raise CloudifyLifecycleError(f"Missing required Cloudify config: {', '.join(missing)}")
    return Config(
        manager_url=str(manager_url),
        username=str(username),
        password=str(password),
        tenant=str(tenant),
        api_version=str(values.get("api_version") or os.getenv("CFY_API_VERSION") or "v3.1"),
        insecure=bool_value(values.get("insecure", os.getenv("CFY_INSECURE", "false"))),
        request_timeout_sec=int(values.get("request_timeout_sec", os.getenv("CFY_REQUEST_TIMEOUT_SEC", "60"))),
        execution_timeout_sec=int(values.get("execution_timeout_sec", os.getenv("CFY_EXEC_TIMEOUT_SEC", "3600"))),
        poll_interval_sec=int(values.get("poll_interval_sec", os.getenv("CFY_POLL_INTERVAL_SEC", "10"))),
        retry_count=int(values.get("retry_count", os.getenv("CFY_RETRY_COUNT", "5"))),
        retry_backoff_sec=int(values.get("retry_backoff_sec", os.getenv("CFY_RETRY_BACKOFF_SEC", "2"))),
    )


def validate_request(values: Dict[str, Any], repo_root: Path) -> None:
    operation = str(values.get("operation", "install")).lower()
    if operation not in SUPPORTED_OPERATIONS:
        raise CloudifyLifecycleError(f"Unsupported operation '{operation}'. Supported: {', '.join(sorted(SUPPORTED_OPERATIONS))}")
    if not values.get("deployment_id"):
        raise CloudifyLifecycleError("deployment_id is required")
    if operation in {"install", "update"}:
        for key in ("blueprint_id", "blueprint_dir"):
            if not values.get(key):
                raise CloudifyLifecycleError(f"{key} is required for {operation}")
        blueprint_dir = Path(resolve_path(repo_root, str(values["blueprint_dir"])))
        if not blueprint_dir.is_dir():
            raise CloudifyLifecycleError(f"blueprint_dir does not exist: {blueprint_dir}")
        app_file = blueprint_dir / str(values.get("application_file", "blueprint.yaml"))
        if not app_file.exists():
            raise CloudifyLifecycleError(f"application_file not found inside blueprint_dir: {app_file}")
    if operation == "execute" and not values.get("workflow"):
        raise CloudifyLifecycleError("workflow is required for execute operation")
    for item in values.get("inputs_files") or []:
        path = Path(resolve_path(repo_root, item))
        if not path.exists():
            raise CloudifyLifecycleError(f"inputs_file not found: {path}")


def run_lifecycle(values: Dict[str, Any], request_file: str, repo_root: Path, audit: Audit) -> None:
    validate_request(values, repo_root)
    cfg = build_config(values)
    dry_run = bool_value(values.get("dry_run", False))
    operation = str(values.get("operation", "install")).lower()
    blueprint_id = values.get("blueprint_id")
    deployment_id = str(values.get("deployment_id"))
    workflow = values.get("workflow")
    wait = bool_value(values.get("wait", True))
    parameters = values.get("parameters") or {}

    logging.info("Request loaded: %s", request_file)
    logging.info("Request summary: %s", json.dumps(sanitize({
        "operation": operation,
        "deployment_id": deployment_id,
        "blueprint_id": blueprint_id,
        "workflow": workflow,
        "tenant": cfg.tenant,
        "manager_url": cfg.manager_url,
        "wait": wait,
        "dry_run": dry_run,
    }), sort_keys=True))
    audit.event("request_validated", operation=operation, deployment_id=deployment_id, blueprint_id=blueprint_id, workflow=workflow)

    if dry_run:
        logging.info("Dry run enabled; no Cloudify API calls will be made")
        audit.event("dry_run_completed")
        return

    client = CloudifyClient(cfg, audit)
    client.authenticate()

    if operation in {"install", "update"}:
        if_blueprint_exists = str(values.get("if_blueprint_exists", "upload")).lower()
        if_deployment_exists = str(values.get("if_deployment_exists", "reuse")).lower()
        blueprint_dir = resolve_path(repo_root, str(values.get("blueprint_dir")))
        application_file = str(values.get("application_file", "blueprint.yaml"))
        client.upload_blueprint(str(blueprint_id), blueprint_dir, application_file, if_exists=if_blueprint_exists)
        inputs = load_inputs(values.get("inputs_files") or [], repo_root)
        client.create_deployment(deployment_id, str(blueprint_id), inputs, if_exists=if_deployment_exists)
        execution_id = client.start_execution(deployment_id, str(workflow or operation), parameters, allow_custom_parameters=bool_value(values.get("allow_custom_parameters", True)))
        if wait:
            client.wait_for_execution(execution_id)
        logging.info("Lifecycle operation completed: %s", operation)
        return

    if operation == "execute":
        execution_id = client.start_execution(deployment_id, str(workflow), parameters, allow_custom_parameters=bool_value(values.get("allow_custom_parameters", True)))
        if wait:
            client.wait_for_execution(execution_id)
        logging.info("Workflow execution completed: %s", workflow)
        return

    if operation == "uninstall":
        if not client.exists(f"deployments/{deployment_id}"):
            logging.info("Deployment '%s' does not exist; uninstall workflow skipped", deployment_id)
            audit.event("uninstall_skipped_missing_deployment", deployment_id=deployment_id)
        else:
            execution_id = client.start_execution(deployment_id, str(workflow or "uninstall"), parameters, allow_custom_parameters=bool_value(values.get("allow_custom_parameters", True)))
            if wait:
                client.wait_for_execution(execution_id)
        if bool_value(values.get("delete_deployment", False)):
            client.delete_deployment(deployment_id, force=bool_value(values.get("force_delete", False)), ignore_missing=bool_value(values.get("ignore_missing", True)))
        if blueprint_id and bool_value(values.get("delete_blueprint", False)):
            client.delete_blueprint(str(blueprint_id), force=bool_value(values.get("force_delete", False)), ignore_missing=bool_value(values.get("ignore_missing", True)))
        logging.info("Uninstall operation completed")
        return

    if operation == "delete":
        if bool_value(values.get("delete_deployment", True)):
            client.delete_deployment(deployment_id, force=bool_value(values.get("force_delete", False)), ignore_missing=bool_value(values.get("ignore_missing", True)))
        if blueprint_id and bool_value(values.get("delete_blueprint", False)):
            client.delete_blueprint(str(blueprint_id), force=bool_value(values.get("force_delete", False)), ignore_missing=bool_value(values.get("ignore_missing", True)))
        logging.info("Delete operation completed")
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reusable Cloudify lifecycle runner")
    parser.add_argument("--request", help="Lifecycle request YAML file")
    parser.add_argument("--operation", choices=sorted(SUPPORTED_OPERATIONS))
    parser.add_argument("--manager-url")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--tenant")
    parser.add_argument("--api-version")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--blueprint-id")
    parser.add_argument("--deployment-id")
    parser.add_argument("--blueprint-dir")
    parser.add_argument("--application-file")
    parser.add_argument("--inputs-file", action="append", dest="inputs_files")
    parser.add_argument("--workflow")
    parser.add_argument("--parameters-json", help="Workflow parameters as JSON object")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--delete-deployment", action="store_true")
    parser.add_argument("--delete-blueprint", action="store_true")
    parser.add_argument("--force-delete", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = repo_root_from_request(args.request)
    request_path = str(Path(args.request).resolve()) if args.request else "<cli>"
    values = load_yaml(args.request) if args.request else {}

    cli_values = {
        "operation": args.operation,
        "manager_url": args.manager_url,
        "username": args.username,
        "password": args.password,
        "tenant": args.tenant,
        "api_version": args.api_version,
        "blueprint_id": args.blueprint_id,
        "deployment_id": args.deployment_id,
        "blueprint_dir": args.blueprint_dir,
        "application_file": args.application_file,
        "inputs_files": args.inputs_files,
        "workflow": args.workflow,
        "delete_deployment": args.delete_deployment if args.delete_deployment else None,
        "delete_blueprint": args.delete_blueprint if args.delete_blueprint else None,
        "force_delete": args.force_delete if args.force_delete else None,
        "dry_run": args.dry_run if args.dry_run else None,
    }
    values = merge_dicts(values, cli_values)
    if args.insecure:
        values["insecure"] = True
    if args.wait:
        values["wait"] = True
    if args.no_wait:
        values["wait"] = False
    if args.parameters_json:
        try:
            params = json.loads(args.parameters_json)
        except json.JSONDecodeError as exc:
            raise CloudifyLifecycleError(f"Invalid --parameters-json: {exc}") from exc
        if not isinstance(params, dict):
            raise CloudifyLifecycleError("--parameters-json must be a JSON object")
        values["parameters"] = params

    run_id = str(values.get("run_id") or os.getenv("RUN_ID") or uuid.uuid4().hex[:12])
    log_dir = setup_logging(values, run_id, repo_root)
    audit = Audit(run_id, request_path, log_dir)

    try:
        run_lifecycle(values, request_path, repo_root, audit)
        summary = audit.finish("success")
        logging.info("Audit summary: %s", summary)
    except Exception as exc:
        summary = audit.finish("failed", error=str(exc))
        logging.error("Audit summary: %s", summary)
        raise


if __name__ == "__main__":
    try:
        main()
    except CloudifyLifecycleError as exc:
        logging.error("Cloudify lifecycle error: %s", exc)
        print(f"Cloudify lifecycle error: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr, flush=True)
        sys.exit(130)
