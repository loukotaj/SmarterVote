import json
from pathlib import Path

from shared.forecast_summary import build_chamber_forecasts
from shared.race_catalog import build_race_summary_fields


def test_race_summary_includes_forecast():
    summary = build_race_summary_fields(
        "ga-senate-2026",
        {
            "id": "ga-senate-2026",
            "election_date": "2026-11-03",
            "updated_utc": "2026-06-20T00:00:00Z",
            "candidates": [{"name": "Alice", "party": "Democratic", "incumbent": True}],
            "forecast": {
                "predicted_winner_name": "Alice",
                "predicted_winner_party": "Democratic",
                "win_probability": 0.61,
                "party_probabilities": {"Democratic": 0.61, "Republican": 0.39},
                "margin_estimate": 2.1,
                "rating": "tilt_d",
                "confidence": "medium",
                "rationale": "Alice has a narrow advantage.",
                "based_on_poll_count": 1,
                "generated_at": "2026-06-20T00:00:00Z",
                "model": "openai/gpt-5.4",
                "source_urls": ["https://example.com/poll"],
            },
        },
    )

    assert summary["forecast"]["rating"] == "tilt_d"
    assert summary["forecast"]["predicted_winner_name"] == "Alice"


def test_chamber_forecast_counts_senate_tie_as_republican_control():
    summaries = json.loads((Path(__file__).resolve().parents[1] / "data" / "published" / "summaries.json").read_text())

    forecast = build_chamber_forecasts(summaries)
    senate = forecast["chambers"]["senate"]

    assert senate["projected_seats"]["Democratic"] + senate["projected_seats"]["Republican"] == 100
    assert senate["control_party"] == "Republican"
    assert "50-50 Senate" in senate["narrative"]
    assert senate["competitive_race_count"] >= len(senate["competitive_races"])


def test_new_chamber_forecast_fields():
    summaries = [
        {
            "id": "ga-senate-2026",
            "office": "United States Senate",
            "state": "Georgia",
            "forecast": {
                "predicted_winner_party": "Democratic",
                "win_probability": 0.60,
                "rating": "tilt_d",
                "party_probabilities": {"Democratic": 0.60, "Republican": 0.40},
            },
        },
        {
            "id": "tx-senate-2026",
            "office": "United States Senate",
            "state": "Texas",
            "forecast": {
                "predicted_winner_party": "Republican",
                "win_probability": 0.70,
                "rating": "lean_r",
                "party_probabilities": {"Democratic": 0.30, "Republican": 0.70},
            },
        },
    ]

    forecast = build_chamber_forecasts(
        summaries,
        analyses={
            "senate": {
                "bottom_line": "Custom bottom line.",
                "why_party_favored": "Custom why favored.",
                "opposing_party_path": "Custom opposing path.",
                "key_uncertainty": "Custom uncertainty.",
            }
        },
    )
    senate = forecast["chambers"]["senate"]

    assert senate["vp_tiebreak_party"] == "Republican"
    assert senate["bottom_line"] == "Custom bottom line."
    assert senate["why_party_favored"] == "Custom why favored."
    assert senate["opposing_party_path"] == "Custom opposing path."
    assert senate["key_uncertainty"] == "Custom uncertainty."
    assert len(senate["seat_distribution"]) > 0
    for key, val in senate["seat_distribution"].items():
        assert "R-" in key or "D-" in key or key == "50R-50D"
        assert 0.0 <= val <= 1.0
