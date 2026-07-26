"""Behavioral tests for pipeline_client.agent.utils._extract_json.

This is a distinct implementation from pipeline_client.agent.agent._extract_json
(already covered by tests/test_json_extraction.py) and exercises its own
bracket-walking fallback, so it needs its own coverage.
"""

import json

import pytest

from pipeline_client.agent.utils import _extract_json


def test_extract_json_plain_object():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_strips_fences_with_language_tag():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_strips_fences_without_language_tag():
    assert _extract_json('```\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_walks_balanced_object_with_trailing_prose():
    """The model appended an explanation after the JSON object; the walker
    should find the matching closing brace and ignore the trailing text."""
    text = '{"id": "abc", "values": [1, 2, 3]} -- this is the final answer.'
    assert _extract_json(text) == {"id": "abc", "values": [1, 2, 3]}


def test_extract_json_walks_balanced_array_when_no_object_present():
    text = "Sure thing! [1, 2, 3] is the array you asked for."
    assert _extract_json(text) == [1, 2, 3]


def test_extract_json_ignores_braces_inside_strings():
    """Braces inside a quoted string value must not confuse the depth counter."""
    text = '{"note": "use a {placeholder} here", "n": 2} trailing'
    assert _extract_json(text) == {"note": "use a {placeholder} here", "n": 2}


def test_extract_json_handles_escaped_quotes_inside_strings():
    text = r'{"note": "she said \"hi\" to {them}"} extra'
    assert _extract_json(text) == {"note": 'she said "hi" to {them}'}


def test_extract_json_invalid_raises_json_decode_error():
    with pytest.raises(json.JSONDecodeError):
        _extract_json("this is not json in any way")


def test_extract_json_unbalanced_braces_raises():
    with pytest.raises(json.JSONDecodeError):
        _extract_json("{unbalanced and never closes")


def test_make_logger_defaults_to_info_for_unknown_level():
    """An unrecognized level string falls back to logging.INFO via getattr default."""
    from pipeline_client.agent.utils import make_logger

    seen = []
    log = make_logger(lambda level, msg: seen.append((level, msg)))
    log("not-a-real-level", "hello world")

    assert seen == [("not-a-real-level", "hello world")]


def test_make_logger_without_callback_does_not_raise():
    from pipeline_client.agent.utils import make_logger

    log = make_logger()
    log("info", "no callback registered")
