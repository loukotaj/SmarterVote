"""Tests for the pipeline run failure taxonomy and health-verdict computation.

Covers: the RunFailureReason/RunHealthStatus enums, placeholder-junk stance
detection, per-step failure bookkeeping on race_json.pipeline_state, the
empty-finance-output silent-failure detector, exception classification, and
the aggregate RunHealthVerdict computed by compute_run_health_verdict.
"""

import pytest

from shared.run_health import (
    RunFailureReason,
    RunHealthStatus,
    RunHealthVerdict,
    StepFailure,
    classify_exception,
    compute_run_health_verdict,
    detect_empty_finance_output,
    get_step_failures,
    is_placeholder_junk_stance,
    record_step_failure,
)

# ---------------------------------------------------------------------------
# Taxonomy shape
# ---------------------------------------------------------------------------


def test_run_failure_reason_covers_required_categories():
    """The taxonomy must cover every category called out in the motivating problem."""
    values = {reason.value for reason in RunFailureReason}
    assert values == {
        "provider_auth_failure",
        "provider_rate_limit",
        "provider_timeout",
        "step_no_data",
        "validation_failed",
        "placeholder_content",
        "roster_verification_failed",
        "budget_exhausted",
        "cancelled",
        "unknown_error",
    }


def test_run_health_status_values():
    assert {s.value for s in RunHealthStatus} == {"healthy", "degraded", "failed", "unknown"}


def test_run_health_verdict_passed_property():
    assert RunHealthVerdict(status=RunHealthStatus.HEALTHY).passed is True
    assert RunHealthVerdict(status=RunHealthStatus.DEGRADED).passed is False
    assert RunHealthVerdict(status=RunHealthStatus.FAILED).passed is False
    assert RunHealthVerdict().passed is False  # default UNKNOWN


def test_run_health_verdict_defaults_are_backward_compatible():
    """Constructing with no arguments (as when a legacy doc lacks the field) must not raise."""
    verdict = RunHealthVerdict()
    assert verdict.status == RunHealthStatus.UNKNOWN
    assert verdict.reasons == []
    assert verdict.step_failures == []
    assert verdict.summary is None


# ---------------------------------------------------------------------------
# Placeholder-junk stance detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stance",
    ["DRAFT", "draft", "  Draft.  ", "TBD", "todo", "TODO", "wip", "n/a", "test", "placeholder", "xxx"],
)
def test_is_placeholder_junk_stance_matches_literal_junk(stance):
    assert is_placeholder_junk_stance(stance) is True


@pytest.mark.parametrize(
    "stance",
    [
        "No public position found after repeated research attempts.",
        "To be determined after review",
        "Supports expanding testing capacity for public health labs.",
        "The candidate has not commented on this issue in detail.",
        "",
        None,
        123,
    ],
)
def test_is_placeholder_junk_stance_does_not_flag_legitimate_or_missing_text(stance):
    assert is_placeholder_junk_stance(stance) is False


# ---------------------------------------------------------------------------
# Per-step failure bookkeeping
# ---------------------------------------------------------------------------


def test_record_step_failure_appends_to_pipeline_state():
    race_json = {}
    record_step_failure(race_json, "finance", RunFailureReason.STEP_NO_DATA, "no donor data for anyone")
    failures = race_json["pipeline_state"]["step_failures"]
    assert failures == [{"step": "finance", "reason": "step_no_data", "detail": "no donor data for anyone"}]


def test_record_step_failure_dedupes_same_step_and_reason():
    """Repeated failures of the same kind (e.g. across retries) must not grow unboundedly."""
    race_json = {}
    for i in range(5):
        record_step_failure(race_json, "issues", RunFailureReason.STEP_NO_DATA, f"attempt {i}")
    failures = race_json["pipeline_state"]["step_failures"]
    assert len(failures) == 1
    assert failures[0]["detail"] == "attempt 0"  # first occurrence wins


def test_record_step_failure_keeps_distinct_reasons_separate():
    race_json = {}
    record_step_failure(race_json, "issues", RunFailureReason.STEP_NO_DATA, "a")
    record_step_failure(race_json, "issues", RunFailureReason.PLACEHOLDER_CONTENT, "b")
    record_step_failure(race_json, "finance", RunFailureReason.STEP_NO_DATA, "c")
    failures = race_json["pipeline_state"]["step_failures"]
    assert len(failures) == 3


def test_record_step_failure_tolerates_non_dict_race_json():
    # Should not raise even if called with something malformed.
    record_step_failure(None, "issues", RunFailureReason.UNKNOWN_ERROR, "x")  # type: ignore[arg-type]


def test_get_step_failures_parses_back_into_models():
    race_json = {"pipeline_state": {"step_failures": [{"step": "finance", "reason": "step_no_data", "detail": None}]}}
    parsed = get_step_failures(race_json)
    assert parsed == [StepFailure(step="finance", reason=RunFailureReason.STEP_NO_DATA, detail=None)]


def test_get_step_failures_tolerates_garbage_entries():
    race_json = {
        "pipeline_state": {
            "step_failures": [
                {"step": "finance", "reason": "step_no_data"},
                "not-a-dict",
                {"step": "finance", "reason": "not-a-real-reason"},
                42,
            ]
        }
    }
    parsed = get_step_failures(race_json)
    assert len(parsed) == 1
    assert parsed[0].step == "finance"


def test_get_step_failures_empty_when_missing():
    assert get_step_failures({}) == []
    assert get_step_failures({"pipeline_state": {}}) == []
    assert get_step_failures({"pipeline_state": {"step_failures": "not-a-list"}}) == []


# ---------------------------------------------------------------------------
# Empty finance output detection (silent failure #1)
# ---------------------------------------------------------------------------


def test_detect_empty_finance_output_true_when_all_candidates_blank():
    race_json = {
        "candidates": [
            {"name": "Alice", "donor_summary": None, "voting_summary": None},
            {"name": "Bob", "donor_summary": "", "voting_summary": ""},
        ]
    }
    assert detect_empty_finance_output(race_json, ["Alice", "Bob"]) is True


def test_detect_empty_finance_output_false_when_any_candidate_has_data():
    race_json = {
        "candidates": [
            {"name": "Alice", "donor_summary": "Raised $2M mostly from PACs.", "voting_summary": None},
            {"name": "Bob", "donor_summary": None, "voting_summary": None},
        ]
    }
    assert detect_empty_finance_output(race_json, ["Alice", "Bob"]) is False


def test_detect_empty_finance_output_false_for_empty_roster():
    assert detect_empty_finance_output({"candidates": []}, []) is False
    assert detect_empty_finance_output({}, []) is False


def test_detect_empty_finance_output_scopes_to_named_candidates():
    """A candidate outside the target list with data must not mask an empty target set."""
    race_json = {
        "candidates": [
            {"name": "Alice", "donor_summary": None, "voting_summary": None},
            {"name": "Untargeted", "donor_summary": "Has data", "voting_summary": "Has data"},
        ]
    }
    assert detect_empty_finance_output(race_json, ["Alice"]) is True


# ---------------------------------------------------------------------------
# Exception classification
# ---------------------------------------------------------------------------


class _FakeProviderError(Exception):
    def __init__(self, message, *, code, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class RunBudgetExceeded(Exception):
    """Named to match pipeline_client.agent.run_budget.RunBudgetExceeded by class name only
    (classify_exception is duck-typed on __class__.__name__, not isinstance)."""


class AgentCancelled(Exception):
    """Named to match pipeline_client.backend.handlers.agent.AgentCancelled by class name only."""


def test_classify_exception_control_flow_by_class_name():
    assert classify_exception(RunBudgetExceeded("timed out")) == RunFailureReason.BUDGET_EXHAUSTED
    assert classify_exception(AgentCancelled("cancelled by admin")) == RunFailureReason.CANCELLED


@pytest.mark.parametrize(
    "code,expected",
    [
        ("auth_failure", RunFailureReason.PROVIDER_AUTH_FAILURE),
        ("quota_exceeded", RunFailureReason.PROVIDER_AUTH_FAILURE),
        ("rate_limited", RunFailureReason.PROVIDER_RATE_LIMIT),
        ("provider_unavailable", RunFailureReason.PROVIDER_TIMEOUT),
        ("connection_failed", RunFailureReason.PROVIDER_TIMEOUT),
    ],
)
def test_classify_exception_duck_types_provider_error_code(code, expected):
    exc = _FakeProviderError("boom", code=code)
    assert classify_exception(exc) == expected


def test_classify_exception_falls_back_to_retryable_flag():
    exc = _FakeProviderError("boom", code="some_new_code_not_mapped", retryable=True)
    assert classify_exception(exc) == RunFailureReason.PROVIDER_TIMEOUT


def test_classify_exception_matches_roster_verification_message():
    exc = ValueError(
        "Refusing to save draft 'ga-senate-2026': new candidate(s) lack qualifying current-cycle "
        "exact-contest evidence: John Smith."
    )
    assert classify_exception(exc) == RunFailureReason.ROSTER_VERIFICATION_FAILED


def test_classify_exception_matches_no_candidates_message():
    exc = ValueError("Refusing to save draft 'ga-senate-2026': 'candidates' is missing or empty.")
    assert classify_exception(exc) == RunFailureReason.STEP_NO_DATA


def test_classify_exception_unknown_by_default():
    assert classify_exception(RuntimeError("something weird happened")) == RunFailureReason.UNKNOWN_ERROR


# ---------------------------------------------------------------------------
# Aggregate verdict
# ---------------------------------------------------------------------------


def test_compute_run_health_verdict_healthy_when_no_failures_and_review_not_required():
    race_json = {"candidates": []}
    verdict = compute_run_health_verdict(race_json, should_review=False, validation_grade=None)
    assert verdict.status == RunHealthStatus.HEALTHY
    assert verdict.passed is True


def test_compute_run_health_verdict_healthy_when_review_passed():
    race_json = {"candidates": []}
    verdict = compute_run_health_verdict(race_json, should_review=True, validation_grade={"grade": "A", "passed": True})
    assert verdict.status == RunHealthStatus.HEALTHY


def test_compute_run_health_verdict_failed_when_review_ran_but_did_not_pass():
    race_json = {"candidates": []}
    verdict = compute_run_health_verdict(race_json, should_review=True, validation_grade={"grade": "F", "passed": False})
    assert verdict.status == RunHealthStatus.FAILED
    assert RunFailureReason.VALIDATION_FAILED in verdict.reasons


def test_compute_run_health_verdict_failed_when_review_ran_but_grade_missing():
    """Review was supposed to run but produced no grade at all — still a failure, not silently healthy."""
    race_json = {"candidates": []}
    verdict = compute_run_health_verdict(race_json, should_review=True, validation_grade=None)
    assert verdict.status == RunHealthStatus.FAILED
    assert RunFailureReason.VALIDATION_FAILED in verdict.reasons


def test_compute_run_health_verdict_degraded_for_soft_failures_only():
    race_json = {}
    record_step_failure(race_json, "finance", RunFailureReason.STEP_NO_DATA, "no donor data for anyone")
    verdict = compute_run_health_verdict(race_json, should_review=False, validation_grade=None)
    assert verdict.status == RunHealthStatus.DEGRADED
    assert verdict.reasons == [RunFailureReason.STEP_NO_DATA]
    assert verdict.step_failures[0].step == "finance"


def test_compute_run_health_verdict_failed_for_hard_failure_reasons():
    race_json = {}
    record_step_failure(race_json, "discovery", RunFailureReason.ROSTER_VERIFICATION_FAILED, "roster check failed")
    verdict = compute_run_health_verdict(race_json, should_review=False, validation_grade=None)
    assert verdict.status == RunHealthStatus.FAILED


def test_compute_run_health_verdict_failed_wins_over_degraded_when_mixed():
    race_json = {}
    record_step_failure(race_json, "finance", RunFailureReason.STEP_NO_DATA, "soft")
    record_step_failure(race_json, "issues", RunFailureReason.PLACEHOLDER_CONTENT, "soft too")
    record_step_failure(race_json, "discovery", RunFailureReason.ROSTER_VERIFICATION_FAILED, "hard")
    verdict = compute_run_health_verdict(race_json, should_review=False, validation_grade=None)
    assert verdict.status == RunHealthStatus.FAILED
    assert len(verdict.reasons) == 3


def test_compute_run_health_verdict_summary_mentions_each_step_failure():
    race_json = {}
    record_step_failure(race_json, "finance", RunFailureReason.STEP_NO_DATA, "no donor data for anyone")
    verdict = compute_run_health_verdict(race_json, should_review=False, validation_grade=None)
    assert "finance" in (verdict.summary or "")
    assert "step_no_data" in (verdict.summary or "")


def test_compute_run_health_verdict_serializes_to_json_safe_dict():
    """model_dump(mode='json') is how callers persist this to Firestore — enums must serialize to strings."""
    race_json = {}
    record_step_failure(race_json, "finance", RunFailureReason.STEP_NO_DATA, "no donor data for anyone")
    verdict = compute_run_health_verdict(race_json, should_review=True, validation_grade={"grade": "F", "passed": False})
    dumped = verdict.model_dump(mode="json")
    assert dumped["status"] == "failed"
    assert set(dumped["reasons"]) == {"step_no_data", "validation_failed"}
    assert dumped["step_failures"][0]["reason"] == "step_no_data"
