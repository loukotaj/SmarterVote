"""Behavioral tests for smartervote_mcp.gcp_launcher.

test_smartervote_mcp_client.py already covers _cloud_run_audience and
configure_cloud_run_identity_token_from_gcp's main happy paths; this file
targets _gcloud_executable, _run_gcloud, _gcloud_project,
configure_admin_key_from_gcp, _is_localhost, and main()'s error handling,
none of which had any coverage before.
"""

from importlib.util import find_spec
from unittest.mock import MagicMock

import pytest

import smartervote_mcp.gcp_launcher as gcp_launcher

# ---------------------------------------------------------------------------
# _gcloud_executable
# ---------------------------------------------------------------------------


def test_gcloud_executable_found_on_path(monkeypatch):
    monkeypatch.setattr(gcp_launcher.shutil, "which", lambda name: "/usr/bin/gcloud" if name == "gcloud" else None)

    assert gcp_launcher._gcloud_executable() == "/usr/bin/gcloud"


def test_gcloud_executable_falls_back_to_gcloud_cmd_on_windows(monkeypatch):
    monkeypatch.setattr(
        gcp_launcher.shutil,
        "which",
        lambda name: "C:\\gcloud.cmd" if name == "gcloud.cmd" else None,
    )

    assert gcp_launcher._gcloud_executable() == "C:\\gcloud.cmd"


def test_gcloud_executable_raises_when_not_found(monkeypatch):
    monkeypatch.setattr(gcp_launcher.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="gcloud was not found on PATH"):
        gcp_launcher._gcloud_executable()


# ---------------------------------------------------------------------------
# _run_gcloud
# ---------------------------------------------------------------------------


def test_run_gcloud_returns_stripped_stdout_on_success(monkeypatch):
    monkeypatch.setattr(gcp_launcher, "_gcloud_executable", lambda: "/usr/bin/gcloud")
    fake_result = MagicMock(returncode=0, stdout="  project-123  \n", stderr="")
    monkeypatch.setattr(gcp_launcher.subprocess, "run", lambda *a, **k: fake_result)

    assert gcp_launcher._run_gcloud(["config", "get-value", "project"]) == "project-123"


def test_run_gcloud_raises_with_stderr_on_failure(monkeypatch):
    monkeypatch.setattr(gcp_launcher, "_gcloud_executable", lambda: "/usr/bin/gcloud")
    fake_result = MagicMock(returncode=1, stdout="", stderr="permission denied\n")
    monkeypatch.setattr(gcp_launcher.subprocess, "run", lambda *a, **k: fake_result)

    with pytest.raises(RuntimeError, match="permission denied"):
        gcp_launcher._run_gcloud(["auth", "print-identity-token"])


def test_run_gcloud_falls_back_to_generic_message_when_no_output(monkeypatch):
    monkeypatch.setattr(gcp_launcher, "_gcloud_executable", lambda: "/usr/bin/gcloud")
    fake_result = MagicMock(returncode=1, stdout="", stderr="")
    monkeypatch.setattr(gcp_launcher.subprocess, "run", lambda *a, **k: fake_result)

    with pytest.raises(RuntimeError, match="gcloud command failed"):
        gcp_launcher._run_gcloud(["whatever"])


# ---------------------------------------------------------------------------
# _gcloud_project
# ---------------------------------------------------------------------------


def test_gcloud_project_returns_configured_project(monkeypatch):
    monkeypatch.setattr(gcp_launcher, "_run_gcloud", lambda args: "my-project")

    assert gcp_launcher._gcloud_project() == "my-project"


def test_gcloud_project_raises_when_unset(monkeypatch):
    monkeypatch.setattr(gcp_launcher, "_run_gcloud", lambda args: "(unset)")

    with pytest.raises(RuntimeError, match="No default gcloud project"):
        gcp_launcher._gcloud_project()


def test_gcloud_project_raises_when_empty(monkeypatch):
    monkeypatch.setattr(gcp_launcher, "_run_gcloud", lambda args: "")

    with pytest.raises(RuntimeError, match="No default gcloud project"):
        gcp_launcher._gcloud_project()


# ---------------------------------------------------------------------------
# configure_admin_key_from_gcp
# ---------------------------------------------------------------------------


def test_configure_admin_key_skips_when_already_set(monkeypatch):
    monkeypatch.setenv("SMARTERVOTE_RACES_API_ADMIN_KEY", "already-set")
    calls = []
    monkeypatch.setattr(gcp_launcher, "_run_gcloud", lambda args: calls.append(args) or "unused")

    gcp_launcher.configure_admin_key_from_gcp()

    assert calls == []


def test_configure_admin_key_fetches_secret_and_sets_env(monkeypatch):
    monkeypatch.delenv("SMARTERVOTE_RACES_API_ADMIN_KEY", raising=False)
    monkeypatch.setenv("SMARTERVOTE_GCP_ENVIRONMENT", "dev")
    monkeypatch.setenv("SMARTERVOTE_GCP_PROJECT", "smartervote")
    monkeypatch.delenv("SMARTERVOTE_ADMIN_KEY_SECRET", raising=False)
    calls = []

    def fake_run_gcloud(args):
        calls.append(args)
        return "secret-value"

    monkeypatch.setattr(gcp_launcher, "_run_gcloud", fake_run_gcloud)

    gcp_launcher.configure_admin_key_from_gcp()

    assert calls == [
        [
            "secrets",
            "versions",
            "access",
            "latest",
            "--secret=races-api-admin-key-dev",
            "--project=smartervote",
        ]
    ]
    assert gcp_launcher.os.environ["SMARTERVOTE_RACES_API_ADMIN_KEY"] == "secret-value"
    monkeypatch.delenv("SMARTERVOTE_RACES_API_ADMIN_KEY", raising=False)


def test_configure_admin_key_raises_when_secret_is_empty(monkeypatch):
    monkeypatch.delenv("SMARTERVOTE_RACES_API_ADMIN_KEY", raising=False)
    monkeypatch.setenv("SMARTERVOTE_GCP_PROJECT", "smartervote")
    monkeypatch.setattr(gcp_launcher, "_run_gcloud", lambda args: "")

    with pytest.raises(RuntimeError, match="is empty"):
        gcp_launcher.configure_admin_key_from_gcp()


# ---------------------------------------------------------------------------
# _cloud_run_impersonation_service_account
# ---------------------------------------------------------------------------


def test_cloud_run_impersonation_service_account_uses_explicit_override(monkeypatch):
    monkeypatch.setenv("SMARTERVOTE_RACES_API_IMPERSONATE_SERVICE_ACCOUNT", "custom-sa@project.iam.gserviceaccount.com")

    assert gcp_launcher._cloud_run_impersonation_service_account() == "custom-sa@project.iam.gserviceaccount.com"


def test_cloud_run_impersonation_service_account_none_for_non_run_app_url(monkeypatch):
    monkeypatch.delenv("SMARTERVOTE_RACES_API_IMPERSONATE_SERVICE_ACCOUNT", raising=False)
    monkeypatch.setenv("SMARTERVOTE_RACES_API_URL", "http://127.0.0.1:8080")

    assert gcp_launcher._cloud_run_impersonation_service_account() is None


def test_cloud_run_impersonation_service_account_derives_from_environment_and_project(monkeypatch):
    monkeypatch.delenv("SMARTERVOTE_RACES_API_IMPERSONATE_SERVICE_ACCOUNT", raising=False)
    monkeypatch.setenv("SMARTERVOTE_RACES_API_URL", "https://races-api-dev-abc.a.run.app")
    monkeypatch.setenv("SMARTERVOTE_GCP_ENVIRONMENT", "dev")
    monkeypatch.setenv("SMARTERVOTE_GCP_PROJECT", "smartervote")

    assert gcp_launcher._cloud_run_impersonation_service_account() == "races-api-dev@smartervote.iam.gserviceaccount.com"


# ---------------------------------------------------------------------------
# _is_localhost
# ---------------------------------------------------------------------------


def test_is_localhost_empty_string_is_true():
    assert gcp_launcher._is_localhost("") is True


def test_is_localhost_true_for_loopback_hosts():
    assert gcp_launcher._is_localhost("http://localhost:8080") is True
    assert gcp_launcher._is_localhost("http://127.0.0.1:8080") is True


def test_is_localhost_false_for_remote_host():
    assert gcp_launcher._is_localhost("https://races-api-dev.a.run.app") is False


def test_is_localhost_returns_false_on_parse_error(monkeypatch):
    def exploding_urlparse(url):
        raise ValueError("bad url")

    monkeypatch.setattr(gcp_launcher, "urlparse", exploding_urlparse)

    assert gcp_launcher._is_localhost("not a url") is False


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def test_main_warns_and_continues_on_localhost_when_admin_key_setup_fails(monkeypatch, capsys):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")
    monkeypatch.setenv("SMARTERVOTE_RACES_API_URL", "http://127.0.0.1:8080")
    monkeypatch.setattr(gcp_launcher, "configure_admin_key_from_gcp", MagicMock(side_effect=RuntimeError("no gcloud")))
    monkeypatch.setattr(gcp_launcher, "configure_cloud_run_identity_token_from_gcp", MagicMock())
    monkeypatch.setattr("smartervote_mcp.server.main", MagicMock())

    gcp_launcher.main()

    captured = capsys.readouterr()
    assert "Warning" in captured.err


def test_main_exits_on_remote_url_when_admin_key_setup_fails(monkeypatch):
    monkeypatch.setenv("SMARTERVOTE_RACES_API_URL", "https://races-api-dev.a.run.app")
    monkeypatch.setattr(gcp_launcher, "configure_admin_key_from_gcp", MagicMock(side_effect=RuntimeError("no gcloud")))
    monkeypatch.setattr(gcp_launcher, "configure_cloud_run_identity_token_from_gcp", MagicMock())

    with pytest.raises(SystemExit) as exc_info:
        gcp_launcher.main()

    assert exc_info.value.code == 1


def test_main_exits_on_remote_url_when_identity_token_setup_fails(monkeypatch):
    monkeypatch.setenv("SMARTERVOTE_RACES_API_URL", "https://races-api-dev.a.run.app")
    monkeypatch.setattr(gcp_launcher, "configure_admin_key_from_gcp", MagicMock())
    monkeypatch.setattr(
        gcp_launcher,
        "configure_cloud_run_identity_token_from_gcp",
        MagicMock(side_effect=RuntimeError("no token")),
    )

    with pytest.raises(SystemExit) as exc_info:
        gcp_launcher.main()

    assert exc_info.value.code == 1


def test_main_runs_server_when_setup_succeeds(monkeypatch):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")
    monkeypatch.setenv("SMARTERVOTE_RACES_API_URL", "http://127.0.0.1:8080")
    monkeypatch.setattr(gcp_launcher, "configure_admin_key_from_gcp", MagicMock())
    monkeypatch.setattr(gcp_launcher, "configure_cloud_run_identity_token_from_gcp", MagicMock())
    fake_server_main = MagicMock()
    monkeypatch.setattr("smartervote_mcp.server.main", fake_server_main)

    gcp_launcher.main()

    fake_server_main.assert_called_once()
