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
