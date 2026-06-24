#!/usr/bin/env python3
"""
WRCP System Enrollment Lifecycle - CI/CD Integration Demo.
Simulates Wind River Cloud Platform system enrollment operations.
"""
from cloudify import ctx
from cloudify.state import ctx_parameters as inputs

operation = ctx.operation.name.split('.')[-1]
props = ctx.node.properties

ctx.logger.info("=" * 60)
ctx.logger.info(f"WRCP Enrollment Operation: {operation}")
ctx.logger.info("=" * 60)
ctx.logger.info(f"System Name:     {props['system_name']}")
ctx.logger.info(f"System Type:     {props['system_type']}")
ctx.logger.info(f"Auth URL:        {props['auth_url']}")
ctx.logger.info(f"Region:          {props['region_name']}")
ctx.logger.info(f"Admin User:      {props['admin_username']}")
ctx.logger.info(f"Upgrade Policy:  {props['upgrade_policy']}")
ctx.logger.info("-" * 60)

if operation == 'create':
    ctx.logger.info(f"[ENROLL] Discovering system at {props['auth_url']}...")
    ctx.logger.info(f"[ENROLL] Authenticating as {props['admin_username']}...")
    ctx.logger.info(f"[ENROLL] System {props['system_name']} ({props['system_type']}) enrolled successfully.")
    ctx.logger.info(f"[ENROLL] Region '{props['region_name']}' registered in inventory.")

elif operation == 'configure':
    ctx.logger.info(f"[CONFIG] Applying configuration to {props['system_name']}...")
    ctx.logger.info(f"[CONFIG] Setting upgrade policy: {props['upgrade_policy']}")
    ctx.logger.info(f"[CONFIG] Verifying system health...")
    ctx.logger.info(f"[CONFIG] System {props['system_name']} configured successfully.")
    # Log operation kwargs if passed via CI/CD
    if inputs:
        ctx.logger.info(f"[CONFIG] CI/CD provided inputs: {dict(inputs)}")

elif operation == 'start':
    ctx.logger.info(f"[VERIFY] Running post-enrollment verification on {props['system_name']}...")
    ctx.logger.info(f"[VERIFY] Checking API endpoint: {props['auth_url']}")
    ctx.logger.info(f"[VERIFY] Checking region availability: {props['region_name']}")
    ctx.logger.info(f"[VERIFY] All checks passed. System is operational.")

elif operation == 'stop':
    ctx.logger.info(f"[UNENROLL] Preparing to unenroll {props['system_name']}...")
    ctx.logger.info(f"[UNENROLL] Removing from upgrade group...")
    ctx.logger.info(f"[UNENROLL] System marked for removal.")

elif operation == 'delete':
    ctx.logger.info(f"[CLEANUP] Removing system {props['system_name']} from inventory...")
    ctx.logger.info(f"[CLEANUP] Deregistering region '{props['region_name']}'...")
    ctx.logger.info(f"[CLEANUP] Cleanup complete.")

ctx.logger.info("=" * 60)
ctx.logger.info(f"Operation '{operation}' completed successfully.")
ctx.logger.info("=" * 60)
