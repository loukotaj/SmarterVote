"""Launch SmarterVote MCP with GCP auth for the deployed races API."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from urllib.parse import urlparse


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
        stdin=subprocess.DEVNULL,
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


def _cloud_run_audience() -> str | None:
    """Return the Cloud Run audience URL when the MCP targets a deployed run.app service."""
    raw_url = os.getenv("SMARTERVOTE_RACES_API_URL") or os.getenv("RACES_API_URL") or ""
    if not raw_url:
        return None
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc.endswith(".run.app"):
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _cloud_run_impersonation_service_account() -> str | None:
    """Return the service account to impersonate for Cloud Run identity tokens."""
    configured = os.getenv("SMARTERVOTE_RACES_API_IMPERSONATE_SERVICE_ACCOUNT")
    if configured:
        return configured

    audience = _cloud_run_audience()
    if not audience:
        return None

    environment = os.getenv("SMARTERVOTE_GCP_ENVIRONMENT", "dev")
    project = os.getenv("SMARTERVOTE_GCP_PROJECT") or _gcloud_project()
    return f"races-api-{environment}@{project}.iam.gserviceaccount.com"


def configure_cloud_run_identity_token_from_gcp() -> None:
    """Populate a Cloud Run identity token unless already configured.

    The races API may require Cloud Run IAM before the FastAPI app receives the
    request. Use X-Serverless-Authorization for that identity token so the app
    can still receive Auth0 Authorization or X-Admin-Key headers separately.
    """
    if os.getenv("SMARTERVOTE_RACES_API_CLOUD_RUN_ID_TOKEN") or os.getenv("SMARTERVOTE_RACES_API_ID_TOKEN"):
        return

    audience = _cloud_run_audience()
    if not audience:
        return

    use_cloud_run_id_token_env = os.getenv("SMARTERVOTE_RACES_API_USE_CLOUD_RUN_ID_TOKEN")
    if use_cloud_run_id_token_env is not None:
        use_cloud_run_id_token = use_cloud_run_id_token_env.lower() in {"1", "true", "yes"}
    else:
        # Default to True if it is a Cloud Run audience URL
        use_cloud_run_id_token = True

    if not use_cloud_run_id_token and not os.getenv("SMARTERVOTE_RACES_API_IMPERSONATE_SERVICE_ACCOUNT"):
        return

    args = ["auth", "print-identity-token", f"--audiences={audience}"]
    impersonate_service_account = _cloud_run_impersonation_service_account()
    if impersonate_service_account:
        args.append(f"--impersonate-service-account={impersonate_service_account}")

    token = _run_gcloud(args)
    if not token:
        raise RuntimeError(f"gcloud returned an empty identity token for audience {audience}")
    os.environ["SMARTERVOTE_RACES_API_CLOUD_RUN_ID_TOKEN"] = token


def _is_localhost(url: str) -> bool:
    """Check if the given URL points to a local address."""
    if not url:
        return True
    try:
        parsed = urlparse(url)
        return parsed.hostname in {"localhost", "127.0.0.1", "::1", None}
    except Exception:
        return False


def main() -> None:
    """Configure auth and run the MCP server."""
    url = os.getenv("SMARTERVOTE_RACES_API_URL") or os.getenv("RACES_API_URL") or "http://127.0.0.1:8080"
    is_local = _is_localhost(url)

    try:
        configure_admin_key_from_gcp()
    except Exception as exc:
        if is_local:
            print(f"Warning: Failed to configure SmarterVote MCP GCP admin key (targeting localhost): {exc}", file=sys.stderr)
        else:
            print(f"Failed to configure SmarterVote MCP GCP admin key: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

    try:
        configure_cloud_run_identity_token_from_gcp()
    except Exception as exc:
        if is_local:
            print(
                f"Warning: Failed to configure SmarterVote MCP GCP identity token (targeting localhost): {exc}",
                file=sys.stderr,
            )
        else:
            print(f"Failed to configure SmarterVote MCP GCP identity token: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

    from smartervote_mcp.server import main as server_main

    server_main()


if __name__ == "__main__":
    main()
