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
    sanitized = sanitize_log_data({"message": EXPOSED_URL, "nested": ["Bearer abc.def.ghi"]})

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


@pytest.mark.asyncio
async def test_logging_manager_bounds_local_buffers() -> None:
    manager = LoggingManager(buffer_size=2)
    logger = logging.getLogger("test-pipeline-buffer")
    logger.handlers.clear()
    logger.propagate = False
    logger.addHandler(manager.handler)
    logger.setLevel(logging.INFO)

    logger.info("one")
    logger.info("two")
    logger.info("three")

    await manager.broadcast_message({"message": "one"})
    await manager.broadcast_message({"message": "two"})
    await manager.broadcast_message({"message": "three"})

    assert len(manager.log_buffer) == 2
    assert len(manager.status_buffer) == 2
    assert manager.dropped_logs == 2


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
        logger = FirestoreLogger("run-1")
        logger.log("error", EXPOSED_URL, extra={"authorization": "Bearer abc.def.ghi"})
        logger.flush()

    entry = db.batch.return_value.set.call_args.args[1]
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


def test_run_manager_bounds_active_run_logs(monkeypatch) -> None:
    monkeypatch.delenv("FIRESTORE_PROJECT", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("CLOUD_RUN_SERVICE", raising=False)
    monkeypatch.setenv("PIPELINE_RUN_LOG_BUFFER_SIZE", "2")
    manager = RunManager()
    request = RunRequest(payload={"race_id": "test-race"})
    run = manager.create_run(["agent"], request)
    manager.start_run(run.run_id)

    manager.add_run_log(run.run_id, {"message": "one"})
    manager.add_run_log(run.run_id, {"message": "two"})
    manager.add_run_log(run.run_id, {"message": "three"})

    assert [entry["message"] for entry in manager.get_run_logs(run.run_id)] == ["two", "three"]
    assert manager.dropped_log_count == 1
    manager.shutdown()
