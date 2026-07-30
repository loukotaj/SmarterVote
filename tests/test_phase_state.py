from pipeline_client.agent import phase_state


def test_completed_units_repairs_invalid_state_and_deduplicates():
    race = {"pipeline_state": {"completed_units": ["issues:a", "issues:a", 7]}}

    assert phase_state.completed_units(race) == {"issues:a", "7"}

    broken = {"pipeline_state": "invalid"}
    assert phase_state.completed_units(broken) == set()
    assert broken["pipeline_state"] == {"completed_units": []}


def test_mark_unit_complete_is_idempotent():
    race = {}

    phase_state.mark_unit_complete(race, "finance:a")
    phase_state.mark_unit_complete(race, "finance:a")

    assert race["pipeline_state"]["completed_units"] == ["finance:a"]


def test_issue_attempts_normalizes_values():
    race = {"pipeline_state": {"issue_attempts": {"a:healthcare": "2", "a:taxes": -4}}}

    attempts = phase_state.issue_attempts(race)

    assert attempts == {"a:healthcare": 2, "a:taxes": 0}
    assert race["pipeline_state"]["issue_attempts"] == attempts


def test_issue_stance_completion_distinguishes_terminal_no_position_from_placeholders():
    assert phase_state.issue_stance_is_complete({"stance": "Supports expanded coverage."})
    assert phase_state.issue_stance_is_complete({"stance": "No public position found after repeated research attempts."})
    assert not phase_state.issue_stance_is_complete({"stance": ""})
    assert not phase_state.issue_stance_is_complete({"stance": "DRAFT"})
    assert not phase_state.issue_stance_is_complete({"stance": "To be determined after review"})


def test_build_handoff_context_includes_recent_work_and_cached_queries():
    context = phase_state.build_handoff_context(
        [{"issue": "Healthcare", "stance": "Supports expanded coverage", "confidence": "high"}],
        {"searches": [{"query": "candidate healthcare policy"}]},
    )

    assert "Healthcare: Supports expanded coverage [high]" in context
    assert '"candidate healthcare policy"' in context
    assert phase_state.build_handoff_context([], None) == "No prior context available."
