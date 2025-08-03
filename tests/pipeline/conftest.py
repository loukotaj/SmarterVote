"""
Test configuration and fixtures for pipeline tests.
"""

import pytest
import asyncio
from datetime import datetime


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_race_id():
    """Mock race ID for testing."""
    return "test-race-2024-mayor-example-city"


@pytest.fixture
def mock_timestamp():
    """Mock timestamp for testing."""
    return datetime(2024, 1, 1, 12, 0, 0)
