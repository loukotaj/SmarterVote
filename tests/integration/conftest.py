"""
Pytest fixtures for integration testing.

This conftest provides:
- Ollama availability checking
- Environment setup for local LLM testing
- Test race configurations
"""

import os
from pathlib import Path
from typing import Generator

import httpx
import pytest

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


# Test race configurations
TEST_RACES = {
    "mi-senate-2026": {
        "state": "Michigan",
        "office": "U.S. Senate",
        "year": 2026,
        "candidates": {
            "democrat": [
                {"name": "Elissa Slotkin", "incumbent": True},
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
