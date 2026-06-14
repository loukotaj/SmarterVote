import logging
from unittest.mock import MagicMock, patch

import pytest

from pipeline_client.agent.utils import make_logger
from pipeline_client.backend.firestore_logger import FirestoreLogger
from pipeline_client.backend.logging_manager import LoggingManager
from pipeline_client.backend.models import RunRequest
from pipeline_client.backend.run_manager import RunManager
from pipeline_client.logging_utils import sanitize_log_data, sanitize_log_message

EXPOSED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/test:generateContent"
    "?key=AIzaSyB19AzqiLp9thAUp6ZqDMXRmy6dLcmUkLo&mode=fast"
)


def test_sanitize_log_message_redacts_credentials() -> None:
    message = (
        f"provider failed for {EXPOSED_URL}; "
        "Authorization: Bearer secret-token-value; "
        "X-API-Key=sk-exampleSecretKey123456789"
    )

    sanitized = sanitize_log_message(message)

    assert "AIzaSy" not in sanitized
    assert "secret-token-value" not in sanitized
    assert "sk-exampleSecretKey" not in sanitized
    assert "key=[REDACTED]" in sanitized
    assert "mode=fast" in sanitized
    assert "Authorization: [REDACTED]" in sanitized


def test_sanitize_log_data_recurses() -> None:
    sanitized = sanitize_log_data({"message": EXPOSED_URL, "nested": [f"Bearer abc.def.ghi"]})

    assert "AIzaSy" not in sanitized["message"]
    assert sanitized["nested"] == ["Bearer [REDACTED]"]


def test_make_logger_sanitizes_callback_message() -> None:
    callback = MagicMock()

    make_logger(callback)("warning", f"request failed: {EXPOSED_URL}")

    callback.assert_called_once()
    assert "AIzaSy" not in callback.call_args.args[1]


@pytest.mark.asyncio
async def test_logging_manager_sanitizes_local_buffers() -> None:
    manager = LoggingManager()
    logger = logging.getLogger("test-pipeline-sanitizer")
    logger.handlers.clear()
    logger.propagate = False
    logger.addHandler(manager.handler)
    logger.setLevel(logging.INFO)

    logger.error("request failed: %s", EXPOSED_URL)
    await manager.broadcast_message({"type": "failed", "error": EXPOSED_URL})

    assert "AIzaSy" not in manager.log_buffer[-1].message
    assert "AIzaSy" not in manager.status_buffer[-1]["error"]


def test_firestore_logger_sanitizes_before_write() -> None:
    log_doc = MagicMock()
    logs_collection = MagicMock()
    logs_collection.document.return_value = log_doc
    run_doc = MagicMock()
    run_doc.collection.return_value = logs_collection
    runs_collection = MagicMock()
    runs_collection.document.return_value = run_doc
    db = MagicMock()
    db.collection.return_value = runs_collection

    with patch("pipeline_client.backend.firestore_logger._get_db", return_value=db):
        FirestoreLogger("run-1").log("error", EXPOSED_URL, extra={"authorization": "Bearer abc.def.ghi"})

    entry = log_doc.set.call_args.args[0]
    assert "AIzaSy" not in entry["message"]
    assert entry["extra"]["authorization"] == "Bearer [REDACTED]"


def test_run_manager_sanitizes_persisted_failure(monkeypatch) -> None:
    monkeypatch.delenv("FIRESTORE_PROJECT", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("CLOUD_RUN_SERVICE", raising=False)
    manager = RunManager()
    request = RunRequest(payload={"race_id": "test-race"})
    run = manager.create_run(["agent"], request)
    manager.start_run(run.run_id)

    failed = manager.fail_run(run.run_id, f"provider failed: {EXPOSED_URL}")

    assert failed is not None
    assert "AIzaSy" not in (failed.error or "")
    manager.shutdown()
