from cloudify import ctx


def _as_dict(value):
    """Return a normal mutable dict.

    Cloudify context objects can expose read-only dict-like mappings. Calling
    update() on those objects may raise "Cannot override read only properties".
    Always copy into a plain Python dict before merging/reading.
    """
    if value is None:
        return {}
    try:
        return dict(value)
    except Exception:
        return {}


def _node_properties():
    """Read deployment inputs mapped to node properties.

    This works for normal lifecycle workflows such as install/uninstall.
    """
    node = getattr(ctx, "node", None)
    return _as_dict(getattr(node, "properties", None)) if node is not None else {}


def _operation_kwargs():
    """Read workflow/execute_operation parameters safely.

    We intentionally avoid ctx.operation.inputs because some Cloudify versions
    do not expose it, and operation inputs can conflict with script-runner
    internal/read-only properties.
    """
    operation = getattr(ctx, "operation", None)
    if operation is None:
        return {}
    return _as_dict(getattr(operation, "kwargs", None))


def _get(values, key, default="N/A"):
    value = values.get(key, default)
    return default if value is None else value


values = _node_properties()
values.update(_operation_kwargs())

operation = getattr(ctx, "operation", None)
operation_name = getattr(operation, "name", "workflow-operation") if operation is not None else "workflow-operation"

customer_name = _get(values, "customer_name")
application_name = _get(values, "application_name")
environment = _get(values, "environment")
message = _get(values, "message")
replicas = _get(values, "replicas", 1)

ctx.logger.info("============================================================")
ctx.logger.info("Cloudify GitOps/Jenkins operation execution")
ctx.logger.info("Lifecycle operation               : %s", operation_name)
ctx.logger.info("Deployment ID                     : %s", ctx.deployment.id)
ctx.logger.info("Node ID                           : %s", ctx.node.id)
ctx.logger.info("Node instance ID                  : %s", ctx.instance.id)
ctx.logger.info("User input - customer_name        : %s", customer_name)
ctx.logger.info("User input - application_name     : %s", application_name)
ctx.logger.info("User input - environment          : %s", environment)
ctx.logger.info("User input - replicas             : %s", replicas)
ctx.logger.info("User input - message              : %s", message)
ctx.logger.info("============================================================")

# Keep the script side-effect-safe for all workflows.
# Some Cloudify versions/plugins reject attempts to override read-only properties
# during lifecycle execution, so we only log the Git-provided values here.
ctx.logger.info("GitOps/Jenkins lifecycle logging completed successfully")
