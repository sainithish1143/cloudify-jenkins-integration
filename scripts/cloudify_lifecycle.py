#!/usr/bin/env python3
"""Cloudify environment/workflow lifecycle runner.

Trigger-agnostic by design: the same script is used by GitHub Actions, Jenkins,
local Docker Compose, and manual runs. It consumes a normalized request YAML
created by scripts/gitops_reconcile.py or scripts/manual_lifecycle_from_deployment.py.

Supported operations:
  create_environment  - upload blueprint if needed, create deployment if needed
  execute_workflow    - execute any Cloudify workflow on an existing deployment
  delete_environment  - delete Cloudify deployment, optionally blueprint

The implementation is intentionally idempotent and safe for repeated CI runs.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests
import yaml

RUNNING_EXECUTION_STATUSES = {"pending", "started", "cancelling", "force_cancelling", "kill_cancelling"}
TERMINAL_SUCCESS = {"terminated"}
TERMINAL_FAILURE = {"failed", "cancelled", "force_cancelling", "kill_cancelling", "canceled"}


def _strip(value: Optional[Any]) -> str:
    return ("" if value is None else str(value)).strip()


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def expand_env(value: Any) -> Any:
    """Expand ${VAR} and ${VAR:-default} in YAML values."""
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    if isinstance(value, str):
        pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}")
        def repl(match: re.Match[str]) -> str:
            return _strip(os.getenv(match.group(1), match.group(3) or ""))
        return pattern.sub(repl, value).strip()
    return value


def load_yaml(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML must be an object: {path}")
    return data


def merge_yaml_files(files: Iterable[Path]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for file_path in files:
        data = load_yaml(file_path)
        merged.update(data)
    return merged


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]


def setup_logging(log_dir: Path, level: str, run_id: str) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("cloudify-lifecycle")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    file_handler = logging.FileHandler(log_dir / f"cloudify-lifecycle-{run_id}.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger


@dataclass
class LifecycleRequest:
    operation: str
    manager_url: str
    username: str
    password: str
    tenant: str
    api_version: str
    insecure: bool
    blueprint_id: str
    deployment_id: str
    blueprint_dir: Path
    application_file: str
    inputs_files: List[Path]
    inputs: Dict[str, Any]
    workflow: str
    workflow_parameters: Dict[str, Any]
    wait: bool
    request_timeout_sec: int
    execution_timeout_sec: int
    poll_interval_sec: int
    retry_count: int
    retry_backoff_sec: int
    delete_deployment: bool
    delete_blueprint: bool
    dry_run: bool
    ensure_environment: bool
    force_recreate_environment: bool
    recreate_uninstall_first: bool
    force_upload_blueprint: bool
    wait_for_existing_execution: bool
    log_level: str
    log_dir: Path

    @staticmethod
    def from_dict(raw: Dict[str, Any], base_dir: Path) -> "LifecycleRequest":
        data = expand_env(raw)
        operation = _strip(data.get("operation") or "").lower()
        allowed = {"create_environment", "execute_workflow", "delete_environment", "install", "execute", "delete", "uninstall"}
        if operation not in allowed:
            raise ValueError(f"operation must be one of {sorted(allowed)}")

        blueprint_dir_value = _strip(data.get("blueprint_dir") or "")
        inputs_files = [(base_dir / _strip(p)).resolve() for p in data.get("inputs_files", [])]
        req = LifecycleRequest(
            operation=operation,
            manager_url=_strip(data.get("manager_url") or os.getenv("CFY_MANAGER_URL")).rstrip("/"),
            username=_strip(data.get("username") or os.getenv("CFY_USERNAME")),
            password=_strip(data.get("password") or os.getenv("CFY_PASSWORD")),
            tenant=_strip(data.get("tenant") or os.getenv("CFY_TENANT") or "default_tenant"),
            api_version=_strip(data.get("api_version") or os.getenv("CFY_API_VERSION") or "v3.1"),
            insecure=_bool(data.get("insecure", os.getenv("CFY_INSECURE", "true")), True),
            blueprint_id=_strip(data.get("blueprint_id") or ""),
            deployment_id=_strip(data.get("deployment_id") or ""),
            blueprint_dir=(base_dir / blueprint_dir_value).resolve() if blueprint_dir_value else base_dir,
            application_file=_strip(data.get("application_file") or "blueprint.yaml"),
            inputs_files=inputs_files,
            inputs=data.get("inputs") or {},
            workflow=_strip(data.get("workflow") or ""),
            workflow_parameters=data.get("workflow_parameters") or data.get("parameters") or {},
            wait=_bool(data.get("wait"), True),
            request_timeout_sec=_int(data.get("request_timeout_sec"), 60),
            execution_timeout_sec=_int(data.get("execution_timeout_sec"), 3600),
            poll_interval_sec=_int(data.get("poll_interval_sec"), 10),
            retry_count=_int(data.get("retry_count"), 5),
            retry_backoff_sec=_int(data.get("retry_backoff_sec"), 5),
            delete_deployment=_bool(data.get("delete_deployment"), operation in {"delete", "delete_environment", "uninstall"}),
            delete_blueprint=_bool(data.get("delete_blueprint"), False),
            dry_run=_bool(data.get("dry_run"), False),
            ensure_environment=_bool(data.get("ensure_environment"), False),
            force_recreate_environment=_bool(data.get("force_recreate_environment"), False),
            recreate_uninstall_first=_bool(data.get("recreate_uninstall_first"), False),
            force_upload_blueprint=_bool(data.get("force_upload_blueprint"), False),
            wait_for_existing_execution=_bool(data.get("wait_for_existing_execution"), True),
            log_level=_strip(data.get("log_level") or "INFO"),
            log_dir=(base_dir / _strip(data.get("log_dir") or "logs")).resolve(),
        )
        req.validate()
        return req

    def validate(self) -> None:
        missing = [name for name in ["manager_url", "username", "password", "tenant", "api_version", "deployment_id"] if not getattr(self, name)]
        if self.operation != "delete_environment" and not self.blueprint_id:
            missing.append("blueprint_id")
        if missing:
            raise ValueError("Missing required values: " + ", ".join(missing))
        if self.operation in {"create_environment", "install"} or self.ensure_environment:
            if not self.blueprint_dir.is_dir():
                raise FileNotFoundError(f"blueprint_dir not found: {self.blueprint_dir}")
            if not (self.blueprint_dir / self.application_file).is_file():
                raise FileNotFoundError(f"application_file not found: {self.blueprint_dir / self.application_file}")
        for inputs_file in self.inputs_files:
            if not inputs_file.is_file():
                raise FileNotFoundError(f"inputs file not found: {inputs_file}")
        if not isinstance(self.workflow_parameters, dict):
            raise ValueError("workflow_parameters/parameters must be a YAML object")


class CloudifyClient:
    def __init__(self, req: LifecycleRequest, logger: logging.Logger):
        self.req = req
        self.logger = logger
        self.base_url = f"{req.manager_url}/api/{req.api_version}"
        self.session = requests.Session()
        self.session.verify = not req.insecure
        self.session.headers.update({"Tenant": req.tenant})

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}{path}"
        timeout = kwargs.pop("timeout", self.req.request_timeout_sec)
        headers = kwargs.pop("headers", {}) or {}
        headers.setdefault("Tenant", self.req.tenant)
        if "json" in kwargs:
            headers.setdefault("Content-Type", "application/json")
        kwargs.setdefault("auth", (self.req.username, self.req.password))

        last_error: Optional[Exception] = None
        for attempt in range(1, self.req.retry_count + 1):
            try:
                response = self.session.request(method, url, headers=headers, timeout=timeout, **kwargs)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.req.retry_count:
                    self.logger.warning("Cloudify API returned %s for %s %s. Retry %s/%s", response.status_code, method, path, attempt, self.req.retry_count)
                    time.sleep(self.req.retry_backoff_sec * attempt)
                    continue
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.req.retry_count:
                    self.logger.warning("Cloudify API request failed for %s %s: %s. Retry %s/%s", method, path, exc, attempt, self.req.retry_count)
                    time.sleep(self.req.retry_backoff_sec * attempt)
                    continue
                raise
        raise RuntimeError(f"Cloudify request failed: {last_error}")

    def _ensure_ok(self, response: requests.Response, allowed: Iterable[int]) -> requests.Response:
        if response.status_code not in set(allowed):
            raise RuntimeError(f"Cloudify API failure {response.status_code}: {response.text}")
        return response

    def authenticate(self) -> None:
        self.logger.info("Authenticating to Cloudify Manager: %s tenant=%s user=%s", self.req.manager_url, self.req.tenant, self.req.username)
        response = self._request("POST", "/tokens", json={})
        self._ensure_ok(response, {200, 201})
        self.logger.info("Authenticated to Cloudify Manager")

    def blueprint_exists(self, blueprint_id: str) -> bool:
        response = self._request("GET", f"/blueprints/{blueprint_id}")
        if response.status_code == 404:
            return False
        self._ensure_ok(response, {200})
        return True

    def deployment_exists(self, deployment_id: str) -> bool:
        response = self._request("GET", f"/deployments/{deployment_id}")
        if response.status_code == 404:
            return False
        self._ensure_ok(response, {200})
        return True

    def list_running_executions(self) -> List[Dict[str, Any]]:
        params = {"deployment_id": self.req.deployment_id, "_include": "id,status,workflow_id"}
        response = self._request("GET", "/executions", params=params)
        if response.status_code == 404:
            return []
        self._ensure_ok(response, {200})
        data = response.json()
        items = data.get("items", data if isinstance(data, list) else [])
        return [item for item in items if str(item.get("status", "")).lower() in RUNNING_EXECUTION_STATUSES]

    def wait_for_no_running_executions(self) -> None:
        if not self.req.wait_for_existing_execution:
            return
        deadline = time.time() + self.req.execution_timeout_sec
        while time.time() < deadline:
            running = self.list_running_executions()
            if not running:
                return
            self.logger.info("Waiting for existing Cloudify execution(s) to finish: %s", [(e.get("id"), e.get("workflow_id"), e.get("status")) for e in running])
            time.sleep(self.req.poll_interval_sec)
        raise TimeoutError(f"Timed out waiting for existing executions on deployment {self.req.deployment_id}")

    def create_blueprint_zip(self) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="cfy-bp-"))
        root_name = self.req.blueprint_dir.name or "blueprint"
        archive_root = temp_dir / root_name
        shutil.copytree(self.req.blueprint_dir, archive_root, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".DS_Store"))
        zip_path = temp_dir / f"{self.req.blueprint_id}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in archive_root.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(temp_dir))
        top_dirs = {p.parts[0] for p in [Path(i.filename) for i in zipfile.ZipFile(zip_path).infolist()] if p.parts}
        if len(top_dirs) != 1:
            raise RuntimeError(f"Invalid blueprint archive. Expected exactly one top-level directory, got: {top_dirs}")
        return zip_path

    def upload_blueprint(self) -> None:
        if self.req.force_upload_blueprint and self.blueprint_exists(self.req.blueprint_id):
            self.logger.info("force_upload_blueprint=true; deleting existing blueprint '%s' before upload", self.req.blueprint_id)
            self.delete_blueprint(ignore_conflict=True)
        elif self.blueprint_exists(self.req.blueprint_id):
            self.logger.info("Blueprint '%s' already exists; skipping upload", self.req.blueprint_id)
            return

        zip_path = self.create_blueprint_zip()
        self.logger.info("Uploading blueprint '%s' from %s", self.req.blueprint_id, zip_path)
        try:
            with zip_path.open("rb") as handle:
                files = {"blueprint_archive": (zip_path.name, handle, "application/zip")}
                params = {"application_file_name": self.req.application_file}
                response = self._request("PUT", f"/blueprints/{self.req.blueprint_id}", params=params, files=files, timeout=max(self.req.request_timeout_sec, 120))
                if response.status_code == 409:
                    self.logger.info("Blueprint '%s' already exists; treating as idempotent success", self.req.blueprint_id)
                    return
                self._ensure_ok(response, {200, 201})
        finally:
            shutil.rmtree(zip_path.parent, ignore_errors=True)

    def deployment_inputs(self) -> Dict[str, Any]:
        inputs = merge_yaml_files(self.req.inputs_files)
        inputs.update(self.req.inputs)
        return inputs

    def create_deployment(self) -> None:
        inputs = self.deployment_inputs()
        self.logger.info("Creating deployment '%s' from blueprint '%s'", self.req.deployment_id, self.req.blueprint_id)
        self.logger.info("Deployment inputs: %s", json.dumps(inputs, sort_keys=True))
        payload = {"blueprint_id": self.req.blueprint_id, "inputs": inputs}
        response = self._request("PUT", f"/deployments/{self.req.deployment_id}", json=payload)
        if response.status_code == 409:
            self.logger.info("Deployment '%s' already exists; treating create as idempotent success", self.req.deployment_id)
            return
        self._ensure_ok(response, {200, 201})

    def start_execution(self, workflow: str) -> str:
        self.wait_for_no_running_executions()
        payload = {
            "deployment_id": self.req.deployment_id,
            "workflow_id": workflow,
            "parameters": self.req.workflow_parameters or {},
            "allow_custom_parameters": True,
        }
        self.logger.info("Starting workflow '%s' on deployment '%s'", workflow, self.req.deployment_id)
        if self.req.workflow_parameters:
            self.logger.info("Workflow parameters: %s", json.dumps(self.req.workflow_parameters, sort_keys=True))
        for attempt in range(1, self.req.retry_count + 1):
            response = self._request("POST", "/executions", json=payload)
            if response.status_code == 400 and "existing_running_execution" in response.text and attempt < self.req.retry_count:
                self.logger.warning("A Cloudify execution is already running. Waiting and retrying start_execution attempt %s/%s", attempt, self.req.retry_count)
                self.wait_for_no_running_executions()
                continue
            self._ensure_ok(response, {200, 201})
            execution_id = response.json().get("id")
            if not execution_id:
                raise RuntimeError("Execution response did not contain execution id")
            return execution_id
        raise RuntimeError("Unable to start execution after retries")

    def wait_for_execution(self, execution_id: str) -> str:
        deadline = time.time() + self.req.execution_timeout_sec
        last_status = "unknown"
        while time.time() < deadline:
            response = self._request("GET", f"/executions/{execution_id}")
            self._ensure_ok(response, {200})
            status = str(response.json().get("status", "unknown")).lower()
            if status != last_status:
                self.logger.info("Execution %s status: %s", execution_id, status)
                last_status = status
            if status in TERMINAL_SUCCESS:
                return status
            if status in TERMINAL_FAILURE:
                raise RuntimeError(f"Execution {execution_id} ended with status: {status}")
            time.sleep(self.req.poll_interval_sec)
        raise TimeoutError(f"Execution {execution_id} timed out after {self.req.execution_timeout_sec}s")

    def delete_deployment(self) -> None:
        if not self.deployment_exists(self.req.deployment_id):
            self.logger.info("Deployment '%s' already absent", self.req.deployment_id)
            return
        self.wait_for_no_running_executions()
        self.logger.info("Deleting deployment '%s'", self.req.deployment_id)
        for attempt in range(1, self.req.retry_count + 1):
            response = self._request("DELETE", f"/deployments/{self.req.deployment_id}")
            if response.status_code in {400, 409} and "running" in response.text.lower() and attempt < self.req.retry_count:
                self.logger.warning("Deployment delete blocked by running execution. Retry %s/%s", attempt, self.req.retry_count)
                self.wait_for_no_running_executions()
                continue
            if response.status_code == 404:
                self.logger.info("Deployment '%s' already absent", self.req.deployment_id)
                return
            self._ensure_ok(response, {200, 204})
            return

    def delete_blueprint(self, ignore_conflict: bool = False) -> None:
        if not self.req.blueprint_id:
            return
        if not self.blueprint_exists(self.req.blueprint_id):
            self.logger.info("Blueprint '%s' already absent", self.req.blueprint_id)
            return
        self.logger.info("Deleting blueprint '%s'", self.req.blueprint_id)
        response = self._request("DELETE", f"/blueprints/{self.req.blueprint_id}")
        if ignore_conflict and response.status_code in {400, 409}:
            self.logger.warning("Could not delete blueprint '%s' due to conflict; continuing: %s", self.req.blueprint_id, response.text)
            return
        if response.status_code == 404:
            return
        self._ensure_ok(response, {200, 204})


def execute(req: LifecycleRequest, logger: logging.Logger) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "operation": req.operation,
        "blueprint_id": req.blueprint_id,
        "deployment_id": req.deployment_id,
        "workflow": req.workflow,
        "status": "started",
    }
    logger.info("Lifecycle request: operation=%s blueprint_id=%s deployment_id=%s workflow=%s manager=%s tenant=%s user=%s password=%s",
                req.operation, req.blueprint_id, req.deployment_id, req.workflow, req.manager_url, req.tenant, req.username, mask(req.password))
    if req.dry_run:
        logger.info("Dry-run enabled. Validation passed; no Cloudify API calls will be made.")
        summary["status"] = "dry-run"
        return summary

    client = CloudifyClient(req, logger)
    client.authenticate()

    if req.operation == "create_environment":
        exists = client.deployment_exists(req.deployment_id)
        if exists and req.force_recreate_environment:
            logger.info("force_recreate_environment=true; recreating deployment '%s'", req.deployment_id)
            if req.recreate_uninstall_first and req.workflow:
                try:
                    execution_id = client.start_execution(req.workflow)
                    if req.wait:
                        client.wait_for_execution(execution_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Pre-recreate workflow failed or was not required: %s", exc)
            client.delete_deployment()
            exists = False
            if req.force_upload_blueprint:
                client.delete_blueprint(ignore_conflict=True)
        client.upload_blueprint()
        if not exists:
            client.create_deployment()
            logger.info("Cloudify environment/deployment '%s' created", req.deployment_id)
        else:
            logger.info("Cloudify environment/deployment '%s' already exists; create_environment is idempotent", req.deployment_id)

    elif req.operation in {"execute", "execute_workflow", "install"}:
        if not client.deployment_exists(req.deployment_id):
            if req.ensure_environment:
                logger.info("Deployment '%s' not found; ensure_environment=true, creating environment first", req.deployment_id)
                client.upload_blueprint()
                client.create_deployment()
            else:
                raise RuntimeError(f"Deployment not found: {req.deployment_id}. Commit deployment desired-state first or set ensure_environment=true.")
        workflow = req.workflow or ("install" if req.operation == "install" else "")
        if not workflow:
            raise ValueError("workflow is required for execute_workflow")
        execution_id = client.start_execution(workflow)
        summary["execution_id"] = execution_id
        if req.wait:
            summary["execution_status"] = client.wait_for_execution(execution_id)

    elif req.operation == "uninstall":
        # Supported for customers whose blueprint exposes an uninstall workflow.
        if client.deployment_exists(req.deployment_id):
            if req.workflow:
                execution_id = client.start_execution(req.workflow)
                summary["execution_id"] = execution_id
                if req.wait:
                    summary["execution_status"] = client.wait_for_execution(execution_id)
            if req.delete_deployment:
                client.delete_deployment()
        else:
            logger.info("Deployment '%s' already absent; skipping uninstall", req.deployment_id)
        if req.delete_blueprint:
            client.delete_blueprint()

    elif req.operation in {"delete", "delete_environment"}:
        if req.delete_deployment:
            client.delete_deployment()
        if req.delete_blueprint:
            client.delete_blueprint()

    summary["status"] = "success"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute a Cloudify lifecycle request")
    parser.add_argument("--request", required=True, help="Path to normalized lifecycle request YAML")
    args = parser.parse_args()

    base_dir = Path.cwd()
    run_id = uuid.uuid4().hex[:12]
    try:
        request_path = Path(args.request)
        data = load_yaml(request_path)
        log_dir = base_dir / _strip(data.get("log_dir") or "logs")
        logger = setup_logging(log_dir, _strip(data.get("log_level") or "INFO"), run_id)
        req = LifecycleRequest.from_dict(data, base_dir)
        logger.info("Run ID: %s", run_id)
        summary = execute(req, logger)
        summary["run_id"] = run_id
        summary_path = req.log_dir / f"cloudify-lifecycle-{run_id}.summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        logger.info("Lifecycle operation completed successfully. Summary: %s", summary_path)
        return 0
    except Exception as exc:  # noqa: BLE001
        fallback_log_dir = base_dir / "logs"
        fallback_log_dir.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("cloudify-lifecycle")
        if not logger.handlers:
            logger = setup_logging(fallback_log_dir, "INFO", run_id)
        logger.exception("Lifecycle operation failed: %s", exc)
        (fallback_log_dir / f"cloudify-lifecycle-{run_id}.summary.json").write_text(json.dumps({"run_id": run_id, "status": "failed", "error": str(exc)}, indent=2), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
