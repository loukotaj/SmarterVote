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
