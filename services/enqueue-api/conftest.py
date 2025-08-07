"""Pytest configuration for enqueue-api tests."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def mock_pubsub_publisher():
    """Mock Pub/Sub publisher for testing."""
    # Set environment variables first
    os.environ["PROJECT_ID"] = "test-project"
    os.environ["PUBSUB_TOPIC"] = "race-processing"

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


@pytest.fixture(scope="function")
def app_module(mock_pubsub_publisher):
    """Import the app module with mocked dependencies."""
    # Clear any cached modules
    modules_to_clear = [mod for mod in sys.modules.keys() if mod == "main" or mod.endswith(".main") or "enqueue" in mod]
    for mod in modules_to_clear:
        del sys.modules[mod]

    # Add the current directory to Python path
    current_dir = Path(__file__).parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))

    # Import the app using absolute file import to avoid conflicts
    import importlib.util

    main_path = current_dir / "main.py"
    spec = importlib.util.spec_from_file_location("enqueue_api_main", main_path)
    main_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_module)

    return main_module


@pytest.fixture(scope="function")
def client(app_module):
    """Create a TestClient with mocked Pub/Sub."""
    return TestClient(app_module.app)
