"""Tests for JSON extraction and search tool schema."""

import json

import pytest

from pipeline_client.agent.agent import SEARCH_TOOL, _extract_json

# ---------------------------------------------------------------------------
# JSON extraction tests
# ---------------------------------------------------------------------------


def test_extract_json_plain():
    """Plain JSON is parsed correctly."""
    data = _extract_json('{"id": "test", "candidates": []}')
    assert data == {"id": "test", "candidates": []}


def test_extract_json_fenced():
    """JSON wrapped in markdown fences is extracted."""
    fenced = '```json\n{"id": "test"}\n```'
    data = _extract_json(fenced)
    assert data == {"id": "test"}


def test_extract_json_fenced_no_lang():
    """JSON wrapped in plain fences (no language) is extracted."""
    fenced = '```\n{"id": "test"}\n```'
    data = _extract_json(fenced)
    assert data == {"id": "test"}


def test_extract_json_with_whitespace():
    """JSON with leading/trailing whitespace is parsed."""
    data = _extract_json('  \n {"id": "test"} \n  ')
    assert data == {"id": "test"}


def test_extract_json_nested():
    """Nested JSON objects are parsed correctly."""
    nested = json.dumps({"a": {"b": {"c": [1, 2, 3]}}})
    data = _extract_json(nested)
    assert data["a"]["b"]["c"] == [1, 2, 3]


def test_extract_json_invalid():
    """Invalid JSON raises an error."""
    with pytest.raises(json.JSONDecodeError):
        _extract_json("not json at all")


# ---------------------------------------------------------------------------
# Search tool definition tests
# ---------------------------------------------------------------------------


def test_search_tool_schema():
    """SEARCH_TOOL has the expected structure for OpenAI-compatible function calling."""
    assert SEARCH_TOOL["type"] == "function"
    assert SEARCH_TOOL["function"]["name"] == "web_search"
    assert "query" in SEARCH_TOOL["function"]["parameters"]["properties"]
    assert "query" in SEARCH_TOOL["function"]["parameters"]["required"]
