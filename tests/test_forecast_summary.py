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
    active_states = [
        "Colorado",
        "Delaware",
        "Georgia",
        "Illinois",
        "Maine",
        "Massachusetts",
        "Michigan",
        "Minnesota",
        "New Hampshire",
        "New Jersey",
        "New Mexico",
        "Oregon",
        "Rhode Island",
        "Alabama",
        "Alaska",
        "Arkansas",
        "Florida",
        "Idaho",
        "Iowa",
        "Kansas",
        "Kentucky",
        "Louisiana",
        "Mississippi",
        "Montana",
        "Nebraska",
        "North Carolina",
        "Ohio",
        "Oklahoma",
        "South Carolina",
        "South Dakota",
        "Tennessee",
        "Texas",
        "Wyoming",
    ]
    summaries = [
        {
            "id": f"{state.lower().replace(' ', '-')}-senate-2026",
            "title": f"{state} Senate",
            "office": "United States Senate",
            "state": state,
            "forecast": {
                "predicted_winner_party": "Democratic" if index < 15 else "Republican",
                "win_probability": 0.65,
                "rating": "lean_d" if index < 15 else "lean_r",
            },
        }
        for index, state in enumerate(active_states)
    ]

    forecast = build_chamber_forecasts(summaries)
    senate = forecast["chambers"]["senate"]

    assert senate["projected_seats"]["Democratic"] + senate["projected_seats"]["Republican"] == 100
    assert senate["projected_seats"]["Democratic"] == 50
    assert senate["projected_seats"]["Republican"] == 50
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


def test_default_chamber_story_names_competitive_races():
    summaries = [
        {
            "id": "ga-senate-2026",
            "title": "Georgia Senate",
            "office": "United States Senate",
            "state": "Georgia",
            "forecast": {
                "predicted_winner_party": "Democratic",
                "win_probability": 0.57,
                "rating": "tilt_d",
                "party_probabilities": {"Democratic": 0.57, "Republican": 0.43},
            },
        },
        {
            "id": "tx-senate-2026",
            "title": "Texas Senate",
            "office": "United States Senate",
            "state": "Texas",
            "forecast": {
                "predicted_winner_party": "Republican",
                "win_probability": 0.68,
                "rating": "lean_r",
                "party_probabilities": {"Democratic": 0.32, "Republican": 0.68},
            },
        },
    ]

    forecast = build_chamber_forecasts(summaries)
    senate = forecast["chambers"]["senate"]

    assert "Georgia Senate" in senate["narrative"]
    assert "Texas Senate" in senate["opposing_party_path"]
    assert "competitive races to reach" not in senate["opposing_party_path"]


def test_governor_forecast_other_party_resolves_from_party_probabilities():
    forecast = build_chamber_forecasts(
        [
            {
                "id": "il-governor-2026",
                "title": "Illinois Governor",
                "office": "Governor",
                "state": "Illinois",
                "forecast": {
                    "predicted_winner_party": "Other",
                    "win_probability": 0.55,
                    "rating": "tilt_d",
                    "party_probabilities": {"Democratic": 0.55, "Republican": 0.45},
                },
            }
        ]
    )

    governors = forecast["chambers"]["governors"]

    assert governors["projected_seats"]["Other"] == 0
    assert governors["projected_seats"]["Democratic"] == 7
    assert governors["projected_seats"]["Republican"] == 8
