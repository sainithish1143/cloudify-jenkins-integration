#!/usr/bin/env python3
"""Manual helper for GitHub Actions workflow_dispatch, Jenkins manual job, and local tests."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gitops_reconcile import deployment_to_request, expand_env_vars, load_yaml_file, merge_yaml_files  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Cloudify action from deployment desired-state file")
    parser.add_argument("--deployment", required=True)
    parser.add_argument("--action", required=True, choices=["create-environment", "execute-workflow", "delete-environment"])
    parser.add_argument("--workflow", default="", help="Workflow for execute-workflow, e.g. install, execute_operation, heal, scale")
    parser.add_argument("--parameters-file", default="", help="YAML file containing workflow parameters")
    parser.add_argument("--inject-inputs-as-operation-kwargs", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = Path.cwd()
    dep_spec = load_yaml_file(repo / args.deployment)

    if args.action == "create-environment":
        req = deployment_to_request(dep_spec, "create_environment", repo)
    elif args.action == "delete-environment":
        req = deployment_to_request(dep_spec, "delete_environment", repo, {"operation": "delete_environment", "delete_deployment": True, "delete_blueprint": False})
    else:
        if not args.workflow:
            raise SystemExit("--workflow is required for --action execute-workflow")
        params: Dict[str, Any] = {}
        if args.parameters_file:
            params = yaml.safe_load((repo / args.parameters_file).read_text(encoding="utf-8")) or {}
            if not isinstance(params, dict):
                raise SystemExit("parameters file must contain a YAML object")
        if args.inject_inputs_as_operation_kwargs:
            body = dep_spec.get("spec") or {}
            deployment = body.get("deployment") or {}
            input_values = merge_yaml_files(repo, deployment.get("inputs", []) or [])
            input_values.update(deployment.get("inline_inputs", {}) or {})
            params["operation_kwargs"] = {**input_values, **(params.get("operation_kwargs") or {})}
        req = deployment_to_request(dep_spec, "execute_workflow", repo, {"operation": "execute_workflow", "workflow": args.workflow, "workflow_parameters": params, "ensure_environment": True})

    if args.dry_run:
        req["dry_run"] = True

    temp_dir = Path(tempfile.mkdtemp(prefix="cfy-manual-request-"))
    request_path = temp_dir / "manual.request.yaml"
    request_path.write_text(yaml.safe_dump(expand_env_vars(req), sort_keys=False), encoding="utf-8")
    return subprocess.run([sys.executable, "scripts/cloudify_lifecycle.py", "--request", str(request_path)], cwd=str(repo)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
