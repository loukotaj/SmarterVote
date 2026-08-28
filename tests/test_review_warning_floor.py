from pipeline_client.agent.review import compute_validation_grade


def test_approved_profile_with_many_warnings_stays_publishable():
    grade = compute_validation_grade(
        [
            {
                "model": "reviewer",
                "score": 95,
                "verdict": "approved",
                "flags": [
                    {"field": f"candidates[1].issues.issue_{index}.sources", "severity": "warning"} for index in range(9)
                ],
            }
        ]
    )

    assert grade == {
        "grade": "B",
        "score": 80,
        "passed": True,
        "summary": "Validated by 1/1 reviewers at 80/100 after a 15-point advisory deduction for 9 warning flag(s).",
    }


def _approvals(score: int = 92, count: int = 3):
    return [{"model": f"reviewer-{i}", "verdict": "approved", "score": score, "flags": []} for i in range(count)]


def _race(*, stances: bool):
    issues = (
        {"Healthcare": {"stance": "Supports expanding coverage.", "sources": [{"url": "https://e.com"}]}} if stances else {}
    )
    return {"candidates": [{"name": "A Candidate", "issues": issues}]}


def test_grade_is_withheld_when_the_race_has_no_issue_stances():
    """az-06-house-2026 sat live at A/92 with zero stances for all four candidates.

    Three reviewers approving a race whose substance was never collected reads
    to a voter as "we checked this"; saying nothing is the honest answer.
    """
    assert compute_validation_grade(_approvals(), _race(stances=False)) is None


def test_grade_is_reported_when_stances_exist():
    grade = compute_validation_grade(_approvals(), _race(stances=True))

    assert grade is not None
    assert grade["grade"] == "A"
    assert grade["passed"] is True


def test_grade_without_race_context_is_unchanged():
    """The race argument is optional; existing callers keep their behaviour."""
    grade = compute_validation_grade(_approvals())

    assert grade is not None and grade["grade"] == "A"


def test_a_race_with_no_candidates_still_grades():
    """An empty roster is a different defect and is not this check's business."""
    assert compute_validation_grade(_approvals(), {"candidates": []}) is not None
