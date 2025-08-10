"""Tests for the enqueue API service."""

import importlib.util
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from google.cloud import pubsub_v1


@pytest.fixture
def mock_pubsub_publisher():
    """Mock Pub/Sub publisher for testing."""
    # Set environment variables first
    os.environ["PROJECT_ID"] = "test-project"
    os.environ["PUBSUB_TOPIC"] = "race-processing"
    os.environ["CLOUD_RUN_JOB_NAME"] = "test-race-worker"
    os.environ["REGION"] = "us-central1"

    # Mock the PublisherClient class before any imports
    with patch("google.cloud.pubsub_v1.PublisherClient") as mock_publisher_class:
        mock_publisher = MagicMock()
        mock_publisher_class.return_value = mock_publisher

        # Set up default mock behavior
        mock_publisher.topic_path.return_value = "projects/test-project/topics/race-processing"
        mock_publisher.get_topic.return_value = True

        # Mock publish method
        mock_future = MagicMock()
        mock_future.result.return_value = "test-message-id"
        mock_publisher.publish.return_value = mock_future

        yield mock_publisher


@pytest.fixture
def client(mock_pubsub_publisher):
    """Create a TestClient with mocked Pub/Sub."""
    # Add the current directory to Python path for isolation
    current_dir = Path(__file__).parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))

    # Clear any cached modules that might interfere
    modules_to_clear = [mod for mod in sys.modules.keys() if "main" in mod and "unittest" not in mod]
    for module in modules_to_clear:
        if module in sys.modules:
            del sys.modules[module]

    # Mock Cloud Run client before importing main
    with patch("main.get_run_client") as mock_get_run_client:
        mock_run_client = MagicMock()
        mock_get_run_client.return_value = mock_run_client

        # Mock Cloud Run job execution
        mock_operation = MagicMock()
        mock_operation.name = "test-operation"
        mock_run_client.run_job.return_value = mock_operation
        mock_run_client.job_path.return_value = "projects/test-project/locations/us-central1/jobs/test-race-worker"

        # Import and create TestClient
        import main
        from fastapi.testclient import TestClient

        yield TestClient(main.app)


def test_root_endpoint(client):
    """Test the root health check endpoint."""
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["service"] == "smartervote-enqueue-api"
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_health_check_healthy(client, mock_pubsub_publisher):
    """Test health check when Pub/Sub is healthy."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["service"] == "smartervote-enqueue-api"
    assert data["status"] == "healthy"
    assert data["components"]["pubsub"] == "healthy"
    assert "timestamp" in data

    # Verify that get_topic was called to check Pub/Sub health
    mock_pubsub_publisher.get_topic.assert_called_once()


def test_health_check_pubsub_unhealthy(client, mock_pubsub_publisher):
    """Test health check when Pub/Sub is unhealthy."""
    # Make get_topic raise an exception
    mock_pubsub_publisher.get_topic.side_effect = Exception("Pub/Sub connection failed")

    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["service"] == "smartervote-enqueue-api"
    assert data["status"] == "degraded"
    assert data["components"]["pubsub"] == "unhealthy"
    assert "timestamp" in data


def test_process_race_success(client, mock_pubsub_publisher):
    """Test successful race processing request."""
    request_data = {
        "race_id": "test-race-123",
        "priority": 1,
        "retry_count": 0,
        "metadata": {"source": "test"},
    }

    response = client.post("/process", json=request_data)
    if response.status_code != 200:
        print(f"Response status: {response.status_code}")
        print(f"Response content: {response.text}")
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["race_id"] == "test-race-123"
    assert "job_id" in data
    assert data["job_id"].startswith("job_test-race-123_")
    # New format should have timestamp and random suffix
    job_id_parts = data["job_id"].split("_")
    assert len(job_id_parts) == 4  # job, race_id, timestamp, random_suffix
    assert "enqueued_at" in data
    assert "Race test-race-123 enqueued for processing" in data["message"]

    # Verify Pub/Sub was called correctly
    mock_pubsub_publisher.publish.assert_called_once()
    call_args = mock_pubsub_publisher.publish.call_args

    # Check topic path
    assert call_args[0][0] == "projects/test-project/topics/race-processing"

    # Check message content
    message_bytes = call_args[0][1]
    message_data = json.loads(message_bytes.decode("utf-8"))

    assert message_data["race_id"] == "test-race-123"
    assert message_data["priority"] == 1
    assert message_data["retry_count"] == 0
    assert message_data["metadata"] == {"source": "test"}
    assert message_data["source"] == "enqueue-api"
    assert "job_id" in message_data
    assert "enqueued_at" in message_data


def test_process_race_minimal_request(client, mock_pubsub_publisher):
    """Test race processing with minimal required data."""
    request_data = {"race_id": "minimal-race"}

    response = client.post("/process", json=request_data)
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["race_id"] == "minimal-race"

    # Verify message was published with defaults
    mock_pubsub_publisher.publish.assert_called_once()
    call_args = mock_pubsub_publisher.publish.call_args
    message_bytes = call_args[0][1]
    message_data = json.loads(message_bytes.decode("utf-8"))

    assert message_data["race_id"] == "minimal-race"
    assert message_data["priority"] == 1  # default
    assert message_data["retry_count"] == 0  # default
    assert message_data["metadata"] == {}  # default


def test_process_race_missing_race_id(client):
    """Test race processing without race_id."""
    request_data = {"priority": 1}

    response = client.post("/process", json=request_data)
    assert response.status_code == 422  # Validation error


def test_process_race_pubsub_failure(client, mock_pubsub_publisher):
    """Test race processing when Pub/Sub publish fails."""
    # Make publish raise an exception
    mock_pubsub_publisher.publish.side_effect = Exception("Pub/Sub publish failed")

    request_data = {"race_id": "failing-race"}

    response = client.post("/process", json=request_data)
    assert response.status_code == 500

    data = response.json()
    assert "Failed to enqueue race processing" in data["detail"]


def test_process_race_pubsub_timeout(client, mock_pubsub_publisher):
    """Test race processing when Pub/Sub future times out."""
    # Make future.result() raise a timeout exception
    mock_future = Mock()
    mock_future.result.side_effect = TimeoutError("Future timed out")
    mock_pubsub_publisher.publish.return_value = mock_future

    request_data = {"race_id": "timeout-race"}

    response = client.post("/process", json=request_data)
    assert response.status_code == 500

    data = response.json()
    assert "Failed to enqueue race processing" in data["detail"]


def test_process_race_custom_priority(client, mock_pubsub_publisher):
    """Test race processing with custom priority."""
    request_data = {
        "race_id": "priority-race",
        "priority": 5,
        "retry_count": 2,
        "metadata": {"urgent": True, "source": "manual"},
    }

    response = client.post("/process", json=request_data)
    assert response.status_code == 200

    # Verify message content includes custom values
    call_args = mock_pubsub_publisher.publish.call_args
    message_bytes = call_args[0][1]
    message_data = json.loads(message_bytes.decode("utf-8"))

    assert message_data["priority"] == 5
    assert message_data["retry_count"] == 2
    assert message_data["metadata"]["urgent"] is True
    assert message_data["metadata"]["source"] == "manual"


def test_get_metrics(client):
    """Test metrics endpoint."""
    response = client.get("/metrics")
    assert response.status_code == 200

    data = response.json()
    assert "total_jobs_processed" in data
    assert "jobs_in_queue" in data
    assert "average_processing_time" in data
    assert "error_rate" in data
    assert "timestamp" in data

    # Current implementation returns zeros (TODO)
    assert data["total_jobs_processed"] == 0
    assert data["jobs_in_queue"] == 0
    assert data["average_processing_time"] == 0
    assert data["error_rate"] == 0


def test_cors_headers(client):
    """Test that CORS headers are properly set."""
    # Test with a POST request that should include CORS headers
    request_data = {"race_id": "test-race"}
    response = client.post("/process", json=request_data, headers={"Origin": "http://localhost:3000"})

    # The response should succeed (CORS is configured to allow all origins)
    assert response.status_code == 200


def test_message_serialization(client, mock_pubsub_publisher):
    """Test that complex metadata is properly serialized."""
    complex_metadata = {
        "nested": {"key": "value"},
        "list": [1, 2, 3],
        "boolean": True,
        "null": None,
    }

    request_data = {"race_id": "complex-race", "metadata": complex_metadata}

    response = client.post("/process", json=request_data)
    assert response.status_code == 200

    # Verify the message can be properly serialized and deserialized
    call_args = mock_pubsub_publisher.publish.call_args
    message_bytes = call_args[0][1]
    message_data = json.loads(message_bytes.decode("utf-8"))

    assert message_data["metadata"] == complex_metadata


@patch.dict(os.environ, {}, clear=True)
def test_missing_environment_variables():
    """Test behavior when required environment variables are missing."""
    # Clear PROJECT_ID to test error handling
    if "PROJECT_ID" in os.environ:
        del os.environ["PROJECT_ID"]

    with patch("google.cloud.pubsub_v1.PublisherClient") as mock_publisher_class:
        mock_publisher = Mock()
        mock_publisher_class.return_value = mock_publisher
        mock_publisher.topic_path.return_value = "projects/None/topics/race-processing"

        # Import should still work, but topic_path will have None
        import sys
        from pathlib import Path

        current_dir = Path(__file__).parent
        if str(current_dir) not in sys.path:
            sys.path.insert(0, str(current_dir))

        import importlib.util

        main_path = current_dir / "main.py"
        spec = importlib.util.spec_from_file_location("test_env_main", main_path)
        main_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(main_module)

        client = TestClient(main_module.app)

        # Basic endpoints should still work
        response = client.get("/")
        assert response.status_code == 200


def test_job_id_generation(client, mock_pubsub_publisher):
    """Test that job IDs are unique and properly formatted."""
    request_data = {"race_id": "test-race"}

    # Make multiple requests
    responses = []
    for _ in range(3):
        response = client.post("/process", json=request_data)
        assert response.status_code == 200
        responses.append(response.json())

    # Verify all job IDs are unique
    job_ids = [r["job_id"] for r in responses]
    assert len(set(job_ids)) == 3  # All unique

    # Verify job ID format: job_race-id_timestamp_random
    for job_id in job_ids:
        assert job_id.startswith("job_test-race_")
        parts = job_id.split("_")
        assert len(parts) == 4  # job, race-id, timestamp, random

        # Timestamp should be numeric (milliseconds)
        timestamp_part = parts[2]
        assert timestamp_part.isdigit()
        assert len(timestamp_part) >= 13  # millisecond timestamp length

        # Random suffix should be 6 chars, alphanumeric lowercase
        random_part = parts[3]
        assert len(random_part) == 6
        assert random_part.islower()
        assert random_part.isalnum()


def test_datetime_handling(client, mock_pubsub_publisher):
    """Test that datetime fields are properly handled."""
    request_data = {"race_id": "datetime-test"}

    response = client.post("/process", json=request_data)
    assert response.status_code == 200

    data = response.json()

    # Verify enqueued_at is a valid ISO format datetime
    enqueued_at = data["enqueued_at"]
    # Should be able to parse it back
    parsed_dt = datetime.fromisoformat(enqueued_at.replace("Z", "+00:00") if enqueued_at.endswith("Z") else enqueued_at)
    assert isinstance(parsed_dt, datetime)

    # Check message content too
    call_args = mock_pubsub_publisher.publish.call_args
    message_bytes = call_args[0][1]
    message_data = json.loads(message_bytes.decode("utf-8"))

    message_enqueued_at = message_data["enqueued_at"]
    parsed_msg_dt = datetime.fromisoformat(
        message_enqueued_at.replace("Z", "+00:00") if message_enqueued_at.endswith("Z") else message_enqueued_at
    )
    assert isinstance(parsed_msg_dt, datetime)


# Webhook endpoint tests


def test_webhook_success(client):
    """Test successful webhook processing with base64 encoded data."""
    import base64

    # Create a proper Pub/Sub message with base64 encoded data
    job_data = {
        "job_id": "test-job-123",
        "race_id": "test-race-2024",
        "priority": 1,
        "retry_count": 0,
        "metadata": {},
        "enqueued_at": "2024-08-10T12:00:00Z",
        "source": "enqueue-api",
    }

    encoded_data = base64.b64encode(json.dumps(job_data).encode("utf-8")).decode("utf-8")

    pubsub_message = {
        "message": {"data": encoded_data, "messageId": "test-message-id", "publishTime": "2024-08-10T12:00:00Z"},
        "subscription": "projects/test-project/subscriptions/race-jobs-sub",
    }

    response = client.post("/webhook", json=pubsub_message)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "success"
    assert "test-race-2024" in data["message"]


def test_webhook_with_attributes(client):
    """Test webhook processing with message attributes instead of data."""
    pubsub_message = {
        "message": {
            "attributes": {"job_id": "test-job-456", "race_id": "attributes-race-2024"},
            "messageId": "test-message-id",
            "publishTime": "2024-08-10T12:00:00Z",
        },
        "subscription": "projects/test-project/subscriptions/race-jobs-sub",
    }

    response = client.post("/webhook", json=pubsub_message)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "success"
    assert "attributes-race-2024" in data["message"]


def test_webhook_missing_race_id(client):
    """Test webhook with missing race_id."""
    import base64

    job_data = {
        "job_id": "test-job-123",
        # Missing race_id
        "priority": 1,
    }

    encoded_data = base64.b64encode(json.dumps(job_data).encode("utf-8")).decode("utf-8")

    pubsub_message = {"message": {"data": encoded_data, "messageId": "test-message-id"}}

    response = client.post("/webhook", json=pubsub_message)
    assert response.status_code == 400
    assert "race_id is required" in response.json()["detail"]


def test_webhook_missing_job_id(client):
    """Test webhook with missing job_id."""
    import base64

    job_data = {
        "race_id": "test-race-2024",
        # Missing job_id
        "priority": 1,
    }

    encoded_data = base64.b64encode(json.dumps(job_data).encode("utf-8")).decode("utf-8")

    pubsub_message = {"message": {"data": encoded_data, "messageId": "test-message-id"}}

    response = client.post("/webhook", json=pubsub_message)
    assert response.status_code == 400
    assert "job_id is required" in response.json()["detail"]


def test_webhook_invalid_message_format(client):
    """Test webhook with invalid message format."""
    invalid_message = {"invalid": "format"}

    response = client.post("/webhook", json=invalid_message)
    assert response.status_code == 400
    assert "Invalid Pub/Sub message format" in response.json()["detail"]


def test_webhook_invalid_base64_data(client):
    """Test webhook with invalid base64 data."""
    pubsub_message = {"message": {"data": "invalid-base64-data!!!", "messageId": "test-message-id"}}

    response = client.post("/webhook", json=pubsub_message)
    assert response.status_code == 400
    assert "Failed to decode message data" in response.json()["detail"]
