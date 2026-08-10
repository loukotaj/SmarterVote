"""Regression tests for races-api GCS publish gating."""

import pathlib
import sys
from unittest.mock import patch

import pytest

RACES_API_DIR = pathlib.Path(__file__).parent.parent / "services" / "races-api"
if str(RACES_API_DIR) not in sys.path:
    sys.path.insert(0, str(RACES_API_DIR))

import gcs_helpers  # noqa: E402


def test_publish_allows_review_only_remaining_without_validation_grade():
    polling_only_race = {
        "id": "nh-senate-2026",
        "candidates": [{"name": "Alice"}],
        "pipeline_state": {
            "complete": False,
            "remaining_candidates": [],
            "remaining_steps": ["review"],
        },
    }

    with (
        patch("gcs_helpers._gcs_archive_race"),
        patch("gcs_helpers._gcs_put_race_json", return_value=True) as mock_put,
        patch("gcs_helpers._gcs_delete_race_json", return_value=True),
        patch("firestore_helpers._fs_update_race"),
    ):
        gcs_helpers.publish_race_to_gcs("nh-senate-2026", polling_only_race)

    mock_put.assert_called_once()


def test_publish_rejects_review_only_remaining_with_failed_grade():
    failed_review_race = {
        "id": "nh-senate-2026",
        "candidates": [{"name": "Alice"}],
        "validation_grade": {"grade": "C", "score": 75, "passed": False},
        "pipeline_state": {
            "complete": False,
            "remaining_candidates": [],
            "remaining_steps": ["review"],
        },
    }

    with pytest.raises(ValueError, match="failed validation"):
        gcs_helpers.publish_race_to_gcs("nh-senate-2026", failed_review_race)


def test_publish_allows_review_warnings_with_passing_grade():
    race = {
        "id": "nh-senate-2026",
        "candidates": [{"name": "Alice"}],
        "validation_grade": {"grade": "A", "score": 95, "passed": True},
        "reviews": [
            {
                "model": "automated-profile-quality",
                "verdict": "flagged",
                "flags": [
                    {
                        "field": "candidates[0].summary_sources",
                        "severity": "warning",
                        "concern": "Summary has no sources.",
                    }
                ],
            }
        ],
    }

    with (
        patch("gcs_helpers._gcs_archive_race"),
        patch("gcs_helpers._gcs_put_race_json", return_value=True) as mock_put,
        patch("gcs_helpers._gcs_delete_race_json", return_value=True),
        patch("firestore_helpers._fs_update_race"),
    ):
        gcs_helpers.publish_race_to_gcs("nh-senate-2026", race)

    mock_put.assert_called_once()


def test_publish_rejects_unresolved_error_review_flag():
    race = {
        "id": "nh-senate-2026",
        "candidates": [{"name": "Alice"}],
        "validation_grade": {"grade": "A", "score": 95, "passed": True},
        "reviews": [{"flags": [{"severity": "error", "concern": "Candidate is missing required evidence."}]}],
    }

    with pytest.raises(ValueError, match="unresolved error-severity"):
        gcs_helpers._assert_publishable_race(race)


def test_publish_rejects_review_warnings_with_failing_grade():
    race = {
        "id": "nh-senate-2026",
        "candidates": [{"name": "Alice"}],
        "validation_grade": {"grade": "C", "score": 75, "passed": False},
        "reviews": [{"flags": [{"severity": "warning", "concern": "Summary has no sources."}]}],
    }

    with pytest.raises(ValueError, match="failed validation"):
        gcs_helpers._assert_publishable_race(race)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"candidates": []}, "no named candidates"),
        ({"candidates": [{"name": "Alice"}, {"name": "alice"}]}, "duplicate candidate"),
        (
            {
                "candidates": [{"name": "Alice"}],
                "forecast": {"predicted_winner_name": "Bob"},
            },
            "not present in the candidate roster",
        ),
        (
            {
                "candidates": [{"name": "Alice"}],
                "forecast": {"market_signals": [{"as_of": "2099-01-01T00:00:00Z"}]},
            },
            "future-dated",
        ),
    ],
)
def test_publish_rejects_deterministic_integrity_failures(data, message):
    with pytest.raises(ValueError, match=message):
        gcs_helpers._assert_publishable_race(data)
