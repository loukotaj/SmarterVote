import json

from pipeline_client.agent.source_trace import TRACE_ENV, trace_issue_sources


def _race():
    return {
        "id": "az-house-09-2026",
        "candidates": [
            {
                "name": "Danielle Sterbinsky",
                "issues": {
                    "Education": {
                        "stance": "Supports career-connected education.",
                        "sources": [{"url": "https://example.com/education"}],
                        "research_audit": {"source_count": 1},
                    }
                },
            }
        ],
    }


def test_trace_issue_sources_logs_exact_configured_path(monkeypatch):
    monkeypatch.setenv(TRACE_ENV, "az-house-09-2026|Danielle Sterbinsky|Education")
    messages = []

    trace_issue_sources(_race(), "after_issues", lambda level, message: messages.append((level, message)))

    assert len(messages) == 1
    level, message = messages[0]
    assert level == "info"
    assert "stage=after_issues" in message
    assert "source_count=1 audit_source_count=1" in message
    assert json.dumps([{"url": "https://example.com/education"}], sort_keys=True) in message


def test_trace_issue_sources_is_silent_for_other_races(monkeypatch):
    monkeypatch.setenv(TRACE_ENV, "other-race|Danielle Sterbinsky|Education")
    messages = []

    trace_issue_sources(_race(), "after_issues", lambda level, message: messages.append((level, message)))

    assert messages == []


def test_trace_issue_sources_warns_for_malformed_target(monkeypatch):
    monkeypatch.setenv(TRACE_ENV, "not-a-valid-target")
    messages = []

    trace_issue_sources(_race(), "after_issues", lambda level, message: messages.append((level, message)))

    assert messages == [("warning", f"Ignoring malformed {TRACE_ENV}; expected race_id|candidate_name|issue_name")]
