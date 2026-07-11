"""Cloud Run Job dispatch for pipeline queue items."""

import os
from typing import Any, Dict


def dispatch_pipeline_job(queue_item_id: str) -> Dict[str, Any]:
    """Start one pipeline worker execution scoped to a Firestore queue item."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID") or os.getenv("FIRESTORE_PROJECT")
    region = os.getenv("PIPELINE_JOB_REGION", os.getenv("REGION", "us-central1"))
    job = os.getenv("PIPELINE_JOB_NAME")
    if not project or not job:
        raise RuntimeError("Cloud Run pipeline job is not configured")

    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    url = f"https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job}:run"
    payload = {
        "overrides": {
            "containerOverrides": [
                {
                    "env": [
                        {"name": "QUEUE_ITEM_ID", "value": queue_item_id},
                        {"name": "WORKER_ONCE", "value": "true"},
                        {"name": "WORKER_RUNNER", "value": "cloud_run"},
                    ]
                }
            ],
            "taskCount": 1,
            "timeout": "43200s",
        }
    }
    response = session.post(url, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()
    return {"operation_name": result.get("name"), "metadata": result.get("metadata") or {}}
