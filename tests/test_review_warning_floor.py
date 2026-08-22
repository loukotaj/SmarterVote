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
