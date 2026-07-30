from shared.race_cleanup import cleanup_race_data, validate_forecast_evidence


def test_cleanup_fixes_known_text_artifact_deduplicates_sources_and_seeds_forecast_evidence():
    race = {
        "description": "Candidate advanced after advanced from the primary.  Updated.",
        "polling": [{"source_url": "https://poll.example.com"}],
        "candidates": [
            {
                "name": "Alice",
                "donor_summary": "Reported receipts.",
                "donor_source_url": "https://fec.gov/alice",
                "issues": {
                    "Economy": {
                        "stance": "Supports growth.  ",
                        "sources": [
                            {"url": "https://example.com/policy"},
                            {"url": "https://example.com/policy"},
                        ],
                    }
                },
            }
        ],
        "forecast": {
            "rationale": "Polling and fundraising support the rating.  ",
            "source_urls": [],
            "key_reasons": [" Recent polling.  "],
            "market_signals": [],
        },
    }

    report = cleanup_race_data(race)

    assert race["description"] == "Candidate advanced after advancing from the primary. Updated."
    assert len(race["candidates"][0]["issues"]["Economy"]["sources"]) == 1
    assert race["forecast"]["source_urls"] == ["https://poll.example.com", "https://fec.gov/alice"]
    assert report["text_changes"] >= 3
    assert report["source_duplicates_removed"] == 1
    assert report["forecast_sources_added"] == 2
    assert {item["kind"] for item in race["forecast"]["evidence_lineage"]} == {"polling", "finance"}
    assert all(item["inferred"] is True for item in race["forecast"]["evidence_lineage"])
    assert validate_forecast_evidence(race) is True


def test_forecast_evidence_gate_records_degraded_step_failure():
    race = {
        "pipeline_state": {},
        "forecast": {
            "rationale": "Candidate is favored by race ratings.",
            "source_urls": [],
        },
    }

    assert validate_forecast_evidence(race) is False
    assert race["pipeline_state"]["step_failures"] == [
        {
            "step": "forecast",
            "reason": "step_no_data",
            "detail": "Forecast evidence gaps: missing_explicit_sources",
        }
    ]


def test_forecast_evidence_gate_requires_named_rating_source():
    race = {
        "pipeline_state": {},
        "forecast": {
            "rationale": "Cook Political Report rates this race Lean Republican.",
            "source_urls": ["https://www.fec.gov/data/candidate/H0CA00001/"],
        },
    }

    assert validate_forecast_evidence(race) is False
    assert "missing_cook_source" in race["pipeline_state"]["step_failures"][0]["detail"]


def test_forecast_without_narrative_claims_does_not_require_sources():
    race = {"forecast": {"rating": "tossup", "source_urls": []}}

    assert validate_forecast_evidence(race) is True
