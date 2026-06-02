#!/usr/bin/env python3
"""Trigger-agnostic reconciler for Cloudify envops model.

Same script is used by GitHub Actions and Jenkins.

Model:
  deployments/*.yaml added/modified -> create/register Cloudify environment only
  operations/*.yaml added/modified  -> execute requested workflow on deployment
  deployments/*.yaml deleted        -> delete environment based on policy
  inputs/*.yaml only                -> no action; data is consumed by operations
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml


def _strip(value: Optional[Any]) -> str:
    return ("" if value is None else str(value)).strip()


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def setup_logging(log_dir: Path, run_id: str, level: str = "INFO") -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("gitops-reconcile")
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    file_handler = logging.FileHandler(log_dir / f"gitops-reconcile-{run_id}.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(stream)
    logger.addHandler(file_handler)
    return logger


def run_cmd(cmd: List[str], cwd: Path, check: bool = True) -> str:
    result = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nstdout={result.stdout}\nstderr={result.stderr}")
    return result.stdout


def load_yaml_text(text: str, source: str) -> Dict[str, Any]:
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML must be an object: {source}")
    return data


def load_yaml_file(path: Path) -> Dict[str, Any]:
    return load_yaml_text(path.read_text(encoding="utf-8"), str(path))


def previous_file_content(repo: Path, before: str, path: str) -> str:
    return run_cmd(["git", "show", f"{before}:{path}"], repo, check=True)


def get_changed_files(repo: Path, before: str, after: str) -> List[Tuple[str, str]]:
    output = run_cmd(["git", "diff", "--name-status", before, after], repo, check=True)
    changes: List[Tuple[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0][0]
        path = parts[-1]
        changes.append((status, path))
    return changes


def merge_yaml_files(repo: Path, files: Iterable[str]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for rel in files or []:
        path = repo / rel
        if not path.is_file():
            raise FileNotFoundError(f"Input file referenced by deployment was not found: {rel}")
        merged.update(load_yaml_file(path))
    return merged


def expand_env_vars(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expand_env_vars(v) for v in obj]
    if isinstance(obj, str):
        pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}")
        def repl(match: re.Match[str]) -> str:
            return _strip(os.getenv(match.group(1), match.group(3) or ""))
        return pattern.sub(repl, obj).strip()
    return obj


def validate_deployment_spec(spec: Dict[str, Any], source: str) -> None:
    if spec.get("kind") != "CloudifyDeployment":
        raise ValueError(f"{source}: kind must be CloudifyDeployment")
    body = spec.get("spec") or {}
    if not isinstance(body, dict):
        raise ValueError(f"{source}: spec must be an object")
    deployment = body.get("deployment") or {}
    blueprint = body.get("blueprint") or {}
    if not _strip(deployment.get("id") or (spec.get("metadata") or {}).get("name")):
        raise ValueError(f"{source}: spec.deployment.id or metadata.name is required")
    if not _strip(blueprint.get("source")):
        raise ValueError(f"{source}: spec.blueprint.source is required")


def deployment_to_request(spec: Dict[str, Any], operation: str, repo: Path, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    validate_deployment_spec(spec, "deployment")
    metadata = spec.get("metadata") or {}
    body = spec.get("spec") or {}
    manager = body.get("manager") or {}
    blueprint = body.get("blueprint") or {}
    deployment = body.get("deployment") or {}
    execution = body.get("execution") or {}
    logging_cfg = body.get("logging") or {}
    policies = body.get("policies") or {}

    deployment_id = _strip(deployment.get("id") or metadata.get("name"))
    blueprint_id = _strip(blueprint.get("id") or f"{deployment_id}-bp")

    request = {
        "operation": operation,
        "manager_url": "${CFY_MANAGER_URL}",
        "username": "${CFY_USERNAME}",
        "password": "${CFY_PASSWORD}",
        "tenant": manager.get("tenant", "${CFY_TENANT:-default_tenant}"),
        "api_version": "${CFY_API_VERSION:-v3.1}",
        "insecure": "${CFY_INSECURE:-true}",
        "blueprint_id": blueprint_id,
        "deployment_id": deployment_id,
        "blueprint_dir": blueprint.get("source"),
        "application_file": blueprint.get("application_file", "blueprint.yaml"),
        "inputs_files": deployment.get("inputs", []),
        "inputs": deployment.get("inline_inputs", {}),
        "workflow": "",
        "workflow_parameters": {},
        "wait": True,
        "request_timeout_sec": execution.get("request_timeout_sec", 60),
        "execution_timeout_sec": execution.get("execution_timeout_sec", 3600),
        "poll_interval_sec": execution.get("poll_interval_sec", 10),
        "retry_count": execution.get("retry_count", 5),
        "retry_backoff_sec": execution.get("retry_backoff_sec", 5),
        "delete_deployment": False,
        "delete_blueprint": False,
        "dry_run": body.get("dry_run", False),
        "ensure_environment": False,
        "force_recreate_environment": bool(policies.get("force_recreate_environment", False)),
        "recreate_uninstall_first": bool(policies.get("recreate_uninstall_first", False)),
        "force_upload_blueprint": bool(policies.get("force_upload_blueprint", False)),
        "wait_for_existing_execution": bool(policies.get("wait_for_existing_execution", True)),
        "log_level": logging_cfg.get("level", "INFO"),
        "log_dir": logging_cfg.get("log_dir", "logs"),
    }
    if extra:
        request.update(extra)
    return request


def operation_to_request(op_spec: Dict[str, Any], repo: Path) -> Dict[str, Any]:
    if op_spec.get("kind") != "CloudifyOperation":
        raise ValueError("operation file kind must be CloudifyOperation")
    spec = op_spec.get("spec") or {}
    deployment_ref = _strip(spec.get("deployment_ref"))
    if not deployment_ref:
        raise ValueError("CloudifyOperation spec.deployment_ref is required")
    dep_path = repo / deployment_ref
    if not dep_path.is_file():
        raise FileNotFoundError(f"Operation references missing deployment file: {deployment_ref}")
    dep_spec = load_yaml_file(dep_path)

    workflow = _strip(spec.get("workflow"))
    if not workflow:
        raise ValueError("CloudifyOperation spec.workflow is required")
    parameters = spec.get("parameters") or {}
    if not isinstance(parameters, dict):
        raise ValueError("CloudifyOperation spec.parameters must be an object")
    parameters = dict(parameters)  # make mutable copy

    policy = spec.get("parameter_policy") or {}
    if policy.get("inject_inputs_as_operation_kwargs") is True:
        dep_body = dep_spec.get("spec") or {}
        dep_deployment = dep_body.get("deployment") or {}
        merged_inputs = merge_yaml_files(repo, dep_deployment.get("inputs", []) or [])
        merged_inputs.update(dep_deployment.get("inline_inputs", {}) or {})
        existing_kwargs = parameters.get("operation_kwargs") or {}
        if not isinstance(existing_kwargs, dict):
            raise ValueError("parameters.operation_kwargs must be an object when present")
        parameters["operation_kwargs"] = {**merged_inputs, **existing_kwargs}

    extra = {
        "operation": "execute_workflow",
        "workflow": workflow,
        "workflow_parameters": parameters,
        "wait": spec.get("wait", True),
        "execution_timeout_sec": spec.get("timeout_sec", 3600),
        "ensure_environment": spec.get("ensure_environment", True),
    }
    return deployment_to_request(dep_spec, "execute_workflow", repo, extra)


def write_request(request: Dict[str, Any], temp_dir: Path, name: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in name)
    path = temp_dir / f"{safe}.request.yaml"
    path.write_text(yaml.safe_dump(expand_env_vars(request), sort_keys=False), encoding="utf-8")
    return path


def execute_request(repo: Path, request_path: Path, logger: logging.Logger, dry_run: bool) -> int:
    cmd = [sys.executable, "scripts/cloudify_lifecycle.py", "--request", str(request_path)]
    logger.info("Executing: %s", " ".join(cmd))
    if dry_run:
        logger.info("Dry-run enabled at reconciler level; not invoking lifecycle runner")
        return 0
    return subprocess.run(cmd, cwd=str(repo), text=True).returncode


def build_actions(repo: Path, before: str, changes: List[Tuple[str, str]], logger: logging.Logger) -> List[Tuple[str, str, Dict[str, Any]]]:
    actions: List[Tuple[str, str, Dict[str, Any]]] = []
    for status, path in changes:
        if path.startswith("deployments/") and path.endswith((".yaml", ".yml")):
            if status == "D":
                dep_spec = load_yaml_text(previous_file_content(repo, before, path), f"{before}:{path}")
                policies = ((dep_spec.get("spec") or {}).get("policies") or {})
                deletion_policy = _strip(policies.get("deletion_policy") or "manual")
                if deletion_policy == "manual":
                    raise RuntimeError(f"{path} was deleted but deletion_policy=manual. Use explicit workflow operation or set deletion_policy=delete_only/auto_uninstall_delete.")
                if deletion_policy == "auto_uninstall_delete":
                    extra = {
                        "operation": "uninstall",
                        "workflow": policies.get("uninstall_workflow", "uninstall"),
                        "wait": True,
                        "delete_deployment": True,
                        "delete_blueprint": bool(policies.get("delete_blueprint_on_delete", False)),
                    }
                    actions.append((path, "uninstall", deployment_to_request(dep_spec, "uninstall", repo, extra)))
                elif deletion_policy == "delete_only":
                    extra = {"operation": "delete_environment", "delete_deployment": True, "delete_blueprint": bool(policies.get("delete_blueprint_on_delete", False))}
                    actions.append((path, "delete_environment", deployment_to_request(dep_spec, "delete_environment", repo, extra)))
                else:
                    raise ValueError(f"Unsupported deletion_policy for {path}: {deletion_policy}")
            elif status in {"A", "M", "R", "C"}:
                dep_spec = load_yaml_file(repo / path)
                actions.append((path, "create_environment", deployment_to_request(dep_spec, "create_environment", repo)))
        elif path.startswith("operations/") and path.endswith((".yaml", ".yml")):
            if status == "D":
                logger.info("Operation intent file removed: %s. No Cloudify action is taken for operation deletion.", path)
                continue
            if status in {"A", "M", "R", "C"}:
                op_spec = load_yaml_file(repo / path)
                actions.append((path, "execute_workflow", operation_to_request(op_spec, repo)))
    return actions


def reconcile(repo: Path, before: str, after: str, mode: str, dry_run: bool, logger: logging.Logger) -> int:
    changes = get_changed_files(repo, before, after)
    candidate_changes = [(s, p) for s, p in changes if p.startswith(("deployments/", "operations/")) and p.endswith((".yaml", ".yml"))]
    if not candidate_changes:
        logger.info("No deployment or operation intent changes detected. Nothing to do.")
        return 0
    actions = build_actions(repo, before, candidate_changes, logger)
    if not actions:
        logger.info("No executable Cloudify actions generated.")
        return 0
    if mode == "first" and len(actions) > 1:
        actions = actions[:1]
    elif mode == "fail" and len(actions) > 1:
        raise RuntimeError(f"Multiple actions detected but mode=fail: {[(a, b) for a, b, _ in actions]}")

    priority = {"create_environment": 0, "execute_workflow": 1, "uninstall": 2, "delete_environment": 3}
    actions = sorted(actions, key=lambda item: priority.get(item[1], 99))

    logger.info("Cloudify actions: %s", [(p, op) for p, op, _ in actions])
    temp_dir = Path(tempfile.mkdtemp(prefix="cfy-envops-requests-"))
    failures = 0
    summary = []
    for path, op, request in actions:
        name = f"{Path(path).stem}-{op}"
        request_path = write_request(request, temp_dir, name)
        logger.info("Generated lifecycle request: %s", request_path)
        logger.info("Request summary: operation=%s workflow=%s deployment_id=%s blueprint_id=%s", request.get("operation"), request.get("workflow"), request.get("deployment_id"), request.get("blueprint_id"))
        rc = execute_request(repo, request_path, logger, dry_run)
        summary.append({"path": path, "operation": op, "deployment_id": request.get("deployment_id"), "workflow": request.get("workflow"), "returncode": rc})
        if rc != 0:
            failures += 1

    (repo / "logs").mkdir(exist_ok=True)
    (repo / "logs" / "gitops-reconcile-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile Cloudify environment + operation intent from Git diff")
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--mode", default=os.getenv("GITOPS_MULTI_DEPLOYMENT_MODE", "all"), choices=["all", "first", "fail"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = Path.cwd()
    run_id = uuid.uuid4().hex[:12]
    logger = setup_logging(repo / "logs", run_id, os.getenv("GITOPS_LOG_LEVEL", "INFO"))
    logger.info("Cloudify envops reconcile run_id=%s before=%s after=%s mode=%s", run_id, args.before, args.after, args.mode)
    try:
        return reconcile(repo, args.before, args.after, args.mode, args.dry_run, logger)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Cloudify envops reconcile failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
