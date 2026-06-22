"""Unit tests for cloudify_lifecycle.py"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from cloudify_lifecycle import (
    _strip, _bool, _int, expand_env, load_yaml, merge_yaml_files,
    mask, LifecycleRequest, CloudifyClient
)


class TestUtilityFunctions:
    def test_strip_none(self):
        assert _strip(None) == ""

    def test_strip_string(self):
        assert _strip("  hello  ") == "hello"

    def test_strip_int(self):
        assert _strip(123) == "123"

    def test_bool_true_values(self):
        assert _bool("true") is True
        assert _bool("1") is True
        assert _bool("yes") is True
        assert _bool(True) is True

    def test_bool_false_values(self):
        assert _bool("false") is False
        assert _bool("0") is False
        assert _bool("no") is False
        assert _bool(None, default=False) is False

    def test_bool_default(self):
        assert _bool(None, default=True) is True

    def test_int_valid(self):
        assert _int("42", 0) == 42
        assert _int(10, 0) == 10

    def test_int_invalid(self):
        assert _int("abc", 99) == 99
        assert _int(None, 5) == 5

    def test_expand_env_string(self):
        os.environ["TEST_VAR"] = "hello"
        assert expand_env("${TEST_VAR}") == "hello"
        del os.environ["TEST_VAR"]

    def test_expand_env_dict(self):
        os.environ["MY_VAL"] = "world"
        result = expand_env({"key": "${MY_VAL}"})
        assert result["key"] == "world"
        del os.environ["MY_VAL"]

    def test_expand_env_no_var(self):
        assert expand_env("plain_text") == "plain_text"

    def test_mask_short(self):
        assert mask("ab") == "****"

    def test_mask_long(self):
        result = mask("admin_password")
        assert result.startswith("ad")
        assert result.endswith("rd")
        assert "****" in result

    def test_load_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("key: value\ncount: 3\n")
            f.flush()
            data = load_yaml(Path(f.name))
            assert data["key"] == "value"
            assert data["count"] == 3
        os.unlink(f.name)

    def test_merge_yaml_files(self):
        with tempfile.TemporaryDirectory() as d:
            f1 = Path(d) / "a.yaml"
            f2 = Path(d) / "b.yaml"
            f1.write_text("name: alice\nage: 30\n")
            f2.write_text("age: 31\ncity: ottawa\n")
            result = merge_yaml_files([f1, f2])
            assert result["name"] == "alice"
            assert result["age"] == 31
            assert result["city"] == "ottawa"


class TestLifecycleRequest:
    def test_validate_missing_manager(self):
        req = LifecycleRequest(
            operation="create_environment",
            manager_url="",
            username="admin",
            password="admin",
            tenant="default_tenant",
            api_version="v3.1",
            insecure=True,
            blueprint_id="bp1",
            blueprint_dir=Path("."),
            application_file="blueprint.yaml",
            deployment_id="dep1",
            inputs_files=[],
            inputs={},
            workflow="",
            workflow_parameters={},
            wait=True,
            request_timeout_sec=60,
            execution_timeout_sec=3600,
            poll_interval_sec=10,
            retry_count=3,
            retry_backoff_sec=5,
            log_dir=Path("logs"),
            delete_deployment=False,
            delete_blueprint=False,
            dry_run=False,
            ensure_environment=True,
            force_recreate_environment=False,
            recreate_uninstall_first=False,
            force_upload_blueprint=False,
            wait_for_existing_execution=True,
            log_level="INFO",
        )
        with pytest.raises(ValueError, match="manager_url"):
            req.validate()


class TestCloudifyClient:
    @patch("cloudify_lifecycle.requests.Session")
    def test_authenticate_success(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": "token123"}
        mock_session.request.return_value = mock_response

        req = MagicMock()
        req.manager_url = "http://localhost:9092"
        req.api_version = "v3.1"
        req.username = "admin"
        req.password = "admin"
        req.tenant = "default_tenant"
        req.insecure = True
        req.timeout = 60
        req.retry_count = 1
        req.retry_backoff = 1

        logger = MagicMock()
        client = CloudifyClient(req, logger)
        client.authenticate()
        logger.info.assert_called()

    @patch("cloudify_lifecycle.requests.Session")
    def test_authenticate_failure(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.request.return_value = mock_response

        req = MagicMock()
        req.manager_url = "http://localhost:9092"
        req.api_version = "v3.1"
        req.username = "admin"
        req.password = "wrong"
        req.tenant = "default_tenant"
        req.insecure = True
        req.timeout = 60
        req.retry_count = 1
        req.retry_backoff = 1

        logger = MagicMock()
        client = CloudifyClient(req, logger)
        with pytest.raises(RuntimeError):
            client.authenticate()

    @patch("cloudify_lifecycle.requests.Session")
    def test_blueprint_exists_true(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.request.return_value = mock_response

        req = MagicMock()
        req.manager_url = "http://localhost:9092"
        req.api_version = "v3.1"
        req.tenant = "default_tenant"
        req.insecure = True
        req.timeout = 60
        req.retry_count = 1
        req.retry_backoff = 1

        logger = MagicMock()
        client = CloudifyClient(req, logger)
        client.token = "token123"
        assert client.blueprint_exists("test-bp") is True

    @patch("cloudify_lifecycle.requests.Session")
    def test_blueprint_exists_false(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_session.request.return_value = mock_response

        req = MagicMock()
        req.manager_url = "http://localhost:9092"
        req.api_version = "v3.1"
        req.tenant = "default_tenant"
        req.insecure = True
        req.timeout = 60
        req.retry_count = 1
        req.retry_backoff = 1

        logger = MagicMock()
        client = CloudifyClient(req, logger)
        client.token = "token123"
        assert client.blueprint_exists("nonexistent-bp") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
