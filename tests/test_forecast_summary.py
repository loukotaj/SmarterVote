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
                "market_signals": [
                    {
                        "provider": "kalshi",
                        "market_ticker": "KXGASENATE-26-DEM",
                        "title": "Will a Democrat win the Georgia Senate race?",
                        "matched_to": "Democratic",
                        "matched_party": "Democratic",
                        "implied_probability": 0.6,
                        "as_of": "2026-06-23T12:00:00Z",
                        "confidence": "medium",
                    }
                ],
            },
        },
    )

    assert summary["forecast"]["rating"] == "tilt_d"
    assert summary["forecast"]["predicted_winner_name"] == "Alice"
    assert summary["forecast"]["market_signals"][0]["provider"] == "kalshi"


def test_chamber_forecast_counts_senate_tie_in_republican_probability():
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
            # Tuned so the seat distribution actually peaks at 18 Republican race
            # wins, which lands on 50-50 once the 32 Republican holdovers are added.
            # projected_seats reports that peak, so a fixture that merely gives
            # Republicans more favored races is not enough to produce the tie.
            "forecast": {
                "predicted_winner_party": "Democratic" if index < 13 else "Republican",
                "win_probability": 0.65,
                "rating": "lean_d" if index < 13 else "lean_r",
            },
        }
        for index, state in enumerate(active_states)
    ]

    forecast = build_chamber_forecasts(summaries)
    senate = forecast["chambers"]["senate"]

    assert senate["projected_seats"]["Democratic"] + senate["projected_seats"]["Republican"] == 100
    assert senate["projected_seats"]["Democratic"] == 50
    assert senate["projected_seats"]["Republican"] == 50
    # The point of the fixture: an exact 50-50 is Republican control via the VP.
    assert senate["control_party"] == "Republican"
    assert senate["vp_tiebreak_party"] == "Republican"
    assert senate["outcome_probabilities"]["Republican"] >= senate["outcome_probabilities"]["tie_50_50"]
    assert "50-50 Senate" in senate["narrative"]
    assert senate["competitive_race_count"] >= len(senate["competitive_races"])


def test_chamber_forecast_control_party_tracks_control_probability():
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
                "predicted_winner_party": "Democratic" if index < 14 else "Republican",
                "win_probability": 0.51,
                "rating": "tilt_d" if index < 14 else "tilt_r",
                "party_probabilities": {
                    "Democratic": 0.51 if index < 14 else 0.49,
                    "Republican": 0.49 if index < 14 else 0.51,
                },
            },
        }
        for index, state in enumerate(active_states)
    ]

    senate = build_chamber_forecasts(summaries)["chambers"]["senate"]

    # Republicans are favored in 19 of the 33 races to the Democrats' 14, so a
    # per-race tally would project 51R-49D. The joint distribution peaks the other
    # way, because winning 19 near-coin-flips is far less likely than the tally
    # implies, and projected_seats reports that peak.
    assert senate["projected_seats"] == {"Democratic": 51, "Republican": 49, "Other": 0}
    mode_key = max(senate["seat_distribution"], key=senate["seat_distribution"].get)
    assert mode_key == "51D-49R"
    # control_party is still derived from control probability, never from the
    # projected split.
    assert senate["outcome_probabilities"]["Democratic"] > senate["outcome_probabilities"]["Republican"]
    assert senate["control_party"] == "Democratic"
    assert senate["control_probability"] == senate["outcome_probabilities"]["Democratic"]


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


def test_projected_seats_falls_back_to_tally_when_seats_are_unaccounted():
    """A partial race set must not hand every unrepresented seat to one party.

    projected_seats derives the non-Republican side by subtracting from the
    chamber total, which is only sound when holdovers plus races cover every
    seat. With a single governor race on the books, subtraction would report ~42
    Democratic seats; the per-race tally reports only what it actually saw.
    """
    summaries = [
        {
            "id": "ga-governor-2026",
            "office": "Governor",
            "state": "Georgia",
            "forecast": {
                "predicted_winner_party": "Democratic",
                "win_probability": 0.60,
                "rating": "lean_d",
                "party_probabilities": {"Democratic": 0.60, "Republican": 0.40},
            },
        }
    ]

    governors = build_chamber_forecasts(summaries)["chambers"]["governors"]

    assert sum(governors["projected_seats"].values()) < 50
    assert governors["projected_seats"]["Democratic"] < 42


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


def test_governor_context_exposes_tie_and_distinguishes_projection_from_control_probability():
    from shared.forecast_summary import build_chamber_context

    context = build_chamber_context(
        [{"id": "ga-governor-2026", "title": "Georgia Governor", "forecast": {"rating": "tossup"}}],
        "Governors",
        {
            "control_party": "Democratic",
            "control_probability": 0.409,
            "outcome_probabilities": {"Democratic": 0.409, "Republican": 0.404, "tie_50_50": 0.187},
            "projected_seats": {"Democratic": 24, "Republican": 26},
            "expected_seats": {"Democratic": 24.6, "Republican": 25.0},
        },
    )

    assert "Most likely outright-control party: Democratic (probability: 40.9%)" in context
    assert "Projected Seats: 24 Democratic, 26 Republican" in context
    assert "Probability of a 25-25 tie: 18.7%" in context
    assert "may differ" in context
