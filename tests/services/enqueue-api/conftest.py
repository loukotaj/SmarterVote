"""Test configuration for enqueue API tests."""

import os
import pytest
from unittest.mock import Mock, patch


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    os.environ["PROJECT_ID"] = "test-project"
    os.environ["PUBSUB_TOPIC"] = "test-topic"


@pytest.fixture
def mock_pubsub_publisher():
    """Mock Google Cloud Pub/Sub Publisher client."""
    with patch('google.cloud.pubsub_v1.PublisherClient') as mock_publisher_class:
        mock_publisher = Mock()
        mock_publisher_class.return_value = mock_publisher
        
        # Mock topic path
        mock_publisher.topic_path.return_value = "projects/test-project/topics/test-topic"
        
        # Mock publish method
        mock_future = Mock()
        mock_future.result.return_value = "test-message-id-123"
        mock_publisher.publish.return_value = mock_future
        
        # Mock get_topic for health checks
        mock_publisher.get_topic.return_value = Mock()
        
        yield mock_publisher
