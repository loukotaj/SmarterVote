"""
Pytest fixtures for integration testing with local LLMs and cached Serper data.

This conftest provides:
- Ollama availability checking
- Serper API response caching (write-through cache)
- Environment setup for local LLM testing
"""

import os
from pathlib import Path
from typing import Any, Generator
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from tests.integration.serper_cache import CACHE_DIR, read_cache, write_cache

# Ollama configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_LOCAL_MODEL = os.getenv("LOCAL_LLM_MODEL", "llama3.2:3b")


def is_ollama_available() -> bool:
    """Check if Ollama is running and accessible."""
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        return response.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def has_model(model_name: str) -> bool:
    """Check if a specific model is available in Ollama."""
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        if response.status_code != 200:
            return False

        data = response.json()
        models = [m.get("name", "") for m in data.get("models", [])]

        # Check both exact match and base model name
        return any(model_name in m or m.startswith(model_name.split(":")[0]) for m in models)
    except (httpx.ConnectError, httpx.TimeoutException, ValueError):
        return False


@pytest.fixture(scope="session")
def check_ollama():
    """
    Session-scoped fixture to verify Ollama is available.
    Tests using this fixture will be skipped if Ollama isn't running.
    """
    if not is_ollama_available():
        pytest.skip("Ollama is not running. Start Ollama to run local LLM tests.")

    if not has_model(DEFAULT_LOCAL_MODEL):
        pytest.skip(f"Model '{DEFAULT_LOCAL_MODEL}' not found in Ollama. " f"Run: ollama pull {DEFAULT_LOCAL_MODEL}")

    return True


@pytest.fixture(scope="session")
def local_llm_env() -> Generator[dict[str, str], None, None]:
    """
    Set up environment variables for local LLM testing.
    Restores original environment after tests complete.
    """
    original_env = {
        "LOCAL_LLM_ENABLED": os.environ.get("LOCAL_LLM_ENABLED"),
        "LOCAL_LLM_BASE_URL": os.environ.get("LOCAL_LLM_BASE_URL"),
        "LOCAL_LLM_MODEL": os.environ.get("LOCAL_LLM_MODEL"),
    }

    # Configure for local LLM
    os.environ["LOCAL_LLM_ENABLED"] = "true"
    os.environ["LOCAL_LLM_BASE_URL"] = f"{OLLAMA_BASE_URL}/v1"
    os.environ["LOCAL_LLM_MODEL"] = DEFAULT_LOCAL_MODEL

    env_config = {
        "LOCAL_LLM_ENABLED": "true",
        "LOCAL_LLM_BASE_URL": f"{OLLAMA_BASE_URL}/v1",
        "LOCAL_LLM_MODEL": DEFAULT_LOCAL_MODEL,
    }

    yield env_config

    # Restore original environment
    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def serper_cache_dir(tmp_path: Path) -> Path:
    """Provide a temporary cache directory for tests."""
    cache_dir = tmp_path / "serper_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@pytest.fixture
def persistent_serper_cache() -> Path:
    """
    Use the persistent fixture cache directory.
    This cache is committed to the repo for reproducible tests.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def create_cached_serper_mock(cache_dir: Path, allow_real_requests: bool = True):
    """
    Create a mock for the Serper API that uses file-based caching.

    Args:
        cache_dir: Directory for cache files
        allow_real_requests: If True, make real API calls and cache responses.
                           If False, fail if response not in cache.

    Returns:
        An async function that can replace _search_serper
    """
    from datetime import datetime

    from pipeline.app.schema import Source, SourceType

    async def cached_search_serper(self, query, issue, now: datetime) -> list:  # FreshSearchQuery  # CanonicalIssue
        """Cached version of _search_serper that reads/writes to file cache."""

        # Extract query text from FreshSearchQuery object
        query_text = getattr(query, "text", str(query))
        search_type = "search"

        # Check cache first
        cached = read_cache(query_text, search_type, cache_dir)
        if cached is not None:
            # Convert cached response to Source objects
            organic_results = cached.get("response", {}).get("organic", [])
            sources = []
            for result in organic_results:
                sources.append(
                    Source(
                        url=result.get("link", ""),
                        type=SourceType.FRESH_SEARCH,
                        title=result.get("title", ""),
                        description=result.get("snippet", ""),
                        last_accessed=now,
                        published_at=now,
                        is_fresh=True,
                    )
                )
            return sources

        if not allow_real_requests:
            raise ValueError(
                f"No cached response for query: {query_text!r}. " "Set allow_real_requests=True to fetch from API."
            )

        # Make real API request
        api_key = os.getenv("SERPER_API_KEY")
        if not api_key:
            raise ValueError("SERPER_API_KEY not set and no cached response available")

        num = getattr(query, "max_results", None) or 5

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query_text, "num": num},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        # Cache the response
        write_cache(query_text, data, search_type, cache_dir)

        # Convert to Source objects
        organic_results = data.get("organic", [])
        sources = []
        for result in organic_results:
            sources.append(
                Source(
                    url=result.get("link", ""),
                    type=SourceType.FRESH_SEARCH,
                    title=result.get("title", ""),
                    description=result.get("snippet", ""),
                    last_accessed=now,
                    published_at=now,
                    is_fresh=True,
                )
            )
        return sources

    return cached_search_serper


@pytest.fixture
def mock_serper_cached(persistent_serper_cache: Path):
    """
    Fixture that patches the Serper API to use cached responses.
    Will make real requests and cache them if SERPER_API_KEY is set.
    """
    allow_real = bool(os.getenv("SERPER_API_KEY"))
    cached_fn = create_cached_serper_mock(persistent_serper_cache, allow_real)

    with patch("pipeline.app.utils.search_utils.SearchUtils._search_serper", new=cached_fn):
        yield persistent_serper_cache


@pytest.fixture
def mock_serper_cached_only(persistent_serper_cache: Path):
    """
    Fixture that patches Serper API to ONLY use cached responses.
    Will fail if a query is not in the cache (for CI/reproducible tests).
    """
    cached_fn = create_cached_serper_mock(persistent_serper_cache, allow_real_requests=False)

    with patch("pipeline.app.utils.search_utils.SearchUtils._search_serper", new=cached_fn):
        yield persistent_serper_cache


# Test race configurations
TEST_RACES = {
    "mi-senate-2026": {
        "state": "Michigan",
        "office": "U.S. Senate",
        "year": 2026,
        "candidates": {
            "democrat": [
                {"name": "Elissa Slotkin", "incumbent": True},
                # Additional primary candidates if testing pre-primary
            ],
            "republican": [
                {"name": "Mike Rogers", "incumbent": False},
                {"name": "Tudor Dixon", "incumbent": False},
            ],
        },
        "description": "Michigan Senate 2026 - Elissa Slotkin defending seat won in 2024",
    },
    "test-race": {
        "state": "Test State",
        "office": "Test Office",
        "year": 2026,
        "candidates": {
            "democrat": [{"name": "Test Democrat", "incumbent": False}],
            "republican": [{"name": "Test Republican", "incumbent": False}],
        },
        "description": "Minimal test race for quick validation",
    },
}


@pytest.fixture
def test_race_config():
    """Provide test race configurations."""
    return TEST_RACES


@pytest.fixture
def mi_senate_2026_config():
    """Specific configuration for Michigan Senate 2026 race."""
    return TEST_RACES["mi-senate-2026"]
