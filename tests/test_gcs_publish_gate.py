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
        "validation_grade": {"grade": "C", "score": 75, "passed": False},
        "pipeline_state": {
            "complete": False,
            "remaining_candidates": [],
            "remaining_steps": ["review"],
        },
    }

    with pytest.raises(ValueError, match="failed validation"):
        gcs_helpers.publish_race_to_gcs("nh-senate-2026", failed_review_race)
