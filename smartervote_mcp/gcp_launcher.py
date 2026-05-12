"""Launch SmarterVote MCP with an admin key loaded from GCP Secret Manager."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def _gcloud_executable() -> str:
    """Return a gcloud executable path that works from Python subprocesses."""
    executable = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not executable:
        raise RuntimeError("gcloud was not found on PATH")
    return executable


def _run_gcloud(args: list[str]) -> str:
    """Run gcloud and return stdout."""
    completed = subprocess.run(
        [_gcloud_executable(), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "gcloud command failed"
        raise RuntimeError(message)
    return completed.stdout.strip()


def _gcloud_project() -> str:
    configured = _run_gcloud(["config", "get-value", "project"])
    if not configured or configured == "(unset)":
        raise RuntimeError("No default gcloud project is configured")
    return configured


def configure_admin_key_from_gcp() -> None:
    """Populate SMARTERVOTE_RACES_API_ADMIN_KEY from Secret Manager unless already set."""
    if os.getenv("SMARTERVOTE_RACES_API_ADMIN_KEY"):
        return

    environment = os.getenv("SMARTERVOTE_GCP_ENVIRONMENT", "dev")
    project = os.getenv("SMARTERVOTE_GCP_PROJECT") or _gcloud_project()
    secret = os.getenv("SMARTERVOTE_ADMIN_KEY_SECRET") or f"races-api-admin-key-{environment}"
    admin_key = _run_gcloud(
        [
            "secrets",
            "versions",
            "access",
            "latest",
            f"--secret={secret}",
            f"--project={project}",
        ]
    )
    if not admin_key:
        raise RuntimeError(f"Secret {secret} in project {project} is empty")
    os.environ["SMARTERVOTE_RACES_API_ADMIN_KEY"] = admin_key


def main() -> None:
    """Configure auth and run the MCP server."""
    try:
        configure_admin_key_from_gcp()
    except Exception as exc:
        print(f"Failed to configure SmarterVote MCP admin auth: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    from smartervote_mcp.server import main as server_main

    server_main()


if __name__ == "__main__":
    main()
