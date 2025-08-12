"""Global pytest configuration and fixtures."""

import os
import pytest


def pytest_addoption(parser):
    """Add command-line options for skipping external dependencies."""
    parser.addoption(
        "--skip-external",
        action="store_true",
        default=False,
        help="Skip tests that require external API calls",
    )
    parser.addoption(
        "--skip-llm",
        action="store_true",
        default=False,
        help="Skip tests that require LLM API calls",
    )
    parser.addoption(
        "--skip-network",
        action="store_true",
        default=False,
        help="Skip tests that require network/HTTP calls",
    )
    parser.addoption(
        "--skip-cloud",
        action="store_true",
        default=False,
        help="Skip tests that require cloud services",
    )


def pytest_configure(config):
    """Configure pytest markers based on environment variables and command-line options."""
    # Check environment variables
    skip_external = os.getenv("SKIP_EXTERNAL_APIS", "").lower() in ("true", "1", "yes")
    skip_llm = os.getenv("SKIP_LLM_APIS", "").lower() in ("true", "1", "yes")
    skip_network = os.getenv("SKIP_NETWORK_CALLS", "").lower() in ("true", "1", "yes")
    skip_cloud = os.getenv("SKIP_CLOUD_SERVICES", "").lower() in ("true", "1", "yes")

    # Check command-line options
    if config.getoption("--skip-external"):
        skip_external = True
    if config.getoption("--skip-llm"):
        skip_llm = True
    if config.getoption("--skip-network"):
        skip_network = True
    if config.getoption("--skip-cloud"):
        skip_cloud = True

    # Add markers to skip collections
    markers = []
    if skip_external:
        markers.append("not external_api")
    if skip_llm:
        markers.append("not llm_api")
    if skip_network:
        markers.append("not network")
    if skip_cloud:
        markers.append("not cloud")

    if markers:
        markexpr = " and ".join(markers)
        config.option.markexpr = markexpr if not config.option.markexpr else f"({config.option.markexpr}) and ({markexpr})"


def pytest_runtest_setup(item):
    """Skip individual tests based on markers and environment variables."""
    # Skip external_api tests if environment variable is set
    if item.get_closest_marker("external_api") and os.getenv("SKIP_EXTERNAL_APIS", "").lower() in ("true", "1", "yes"):
        pytest.skip("Skipping external API test (SKIP_EXTERNAL_APIS=true)")

    # Skip llm_api tests if environment variable is set
    if item.get_closest_marker("llm_api") and os.getenv("SKIP_LLM_APIS", "").lower() in ("true", "1", "yes"):
        pytest.skip("Skipping LLM API test (SKIP_LLM_APIS=true)")

    # Skip network tests if environment variable is set
    if item.get_closest_marker("network") and os.getenv("SKIP_NETWORK_CALLS", "").lower() in ("true", "1", "yes"):
        pytest.skip("Skipping network test (SKIP_NETWORK_CALLS=true)")

    # Skip cloud tests if environment variable is set
    if item.get_closest_marker("cloud") and os.getenv("SKIP_CLOUD_SERVICES", "").lower() in ("true", "1", "yes"):
        pytest.skip("Skipping cloud service test (SKIP_CLOUD_SERVICES=true)")


@pytest.fixture
def mock_openai_provider():
    """Mock OpenAI provider for testing."""
    from unittest.mock import AsyncMock, MagicMock

    mock_provider = MagicMock()
    mock_provider.is_enabled = True
    mock_provider.provider_name = "openai"

    # Mock summarize method
    async def mock_summarize(*args, **kwargs):
        return {
            "summary": "Mock healthcare summary for testing",
            "confidence": "high",
            "sources": ["mock-source-1", "mock-source-2"],
        }

    mock_provider.summarize = AsyncMock(side_effect=mock_summarize)
    return mock_provider


@pytest.fixture
def mock_anthropic_provider():
    """Mock Anthropic provider for testing."""
    from unittest.mock import AsyncMock, MagicMock

    mock_provider = MagicMock()
    mock_provider.is_enabled = True
    mock_provider.provider_name = "anthropic"

    # Mock summarize method
    async def mock_summarize(*args, **kwargs):
        return {
            "summary": "Mock economic summary for testing",
            "confidence": "medium",
            "sources": ["mock-source-3", "mock-source-4"],
        }

    mock_provider.summarize = AsyncMock(side_effect=mock_summarize)
    return mock_provider


@pytest.fixture
def mock_xai_provider():
    """Mock XAI (Grok) provider for testing."""
    from unittest.mock import AsyncMock, MagicMock

    mock_provider = MagicMock()
    mock_provider.is_enabled = True
    mock_provider.provider_name = "xai"

    # Mock summarize method
    async def mock_summarize(*args, **kwargs):
        return {
            "summary": "Mock climate summary for testing",
            "confidence": "low",
            "sources": ["mock-source-5", "mock-source-6"],
        }

    mock_provider.summarize = AsyncMock(side_effect=mock_summarize)
    return mock_provider


@pytest.fixture
def mock_all_llm_providers(mock_openai_provider, mock_anthropic_provider, mock_xai_provider):
    """Mock all LLM providers for testing."""
    return {"openai": mock_openai_provider, "anthropic": mock_anthropic_provider, "xai": mock_xai_provider}
