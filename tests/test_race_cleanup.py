from shared.race_cleanup import cleanup_race_data, forecast_evidence_gaps, validate_forecast_evidence


def test_cleanup_removes_null_and_blank_social_media_values():
    race = {
        "candidates": [
            {
                "name": "Candidate",
                "social_media": {
                    "linkedin": None,
                    "facebook": "  ",
                    "website": " https://example.com/candidate ",
                },
            }
        ]
    }

    report = cleanup_race_data(race)

    assert race["candidates"][0]["social_media"] == {"website": "https://example.com/candidate"}
    assert report["invalid_social_links_removed"] == 2


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


def test_forecast_with_no_sources_at_all_is_not_a_health_failure():
    """When search turns up nothing usable, incumbency plus partisan lean is the
    honest basis for a prediction. Saying so should not degrade the run — roughly
    a quarter of lightweight refreshes were being marked degraded for it."""
    race = {
        "pipeline_state": {},
        "forecast": {
            "rationale": "Candidate is favored by the district's partisan lean and incumbency.",
            "source_urls": [],
        },
    }

    assert validate_forecast_evidence(race) is True
    assert race["pipeline_state"].get("step_failures") in (None, [])


def test_missing_explicit_sources_still_reported_as_a_coverage_gap():
    """It stops degrading health but must stay visible as a coverage signal."""
    race = {
        "forecast": {
            "rationale": "Candidate is favored by the district's partisan lean.",
            "source_urls": [],
        },
    }

    assert "missing_explicit_sources" in forecast_evidence_gaps(race)


def test_cleanup_repairs_pathological_repeated_district_description_prefix():
    race = {
        "jurisdiction": "Alabama's 2nd Congressional District",
        "description": (
            "Alabama's 202020202's2's2's2's2's2's2\u0d82\u0b3e's 2nd Congressional District race "
            "is shaped by ongoing redistricting litigation."
        ),
    }

    report = cleanup_race_data(race)

    assert race["description"] == ("Alabama's 2nd Congressional District race is shaped by ongoing redistricting litigation.")
    assert report["text_changes"] == 1


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


def test_cleanup_clears_zero_year_placeholders_from_history_entries():
    """A 0 year is an unknown-value sentinel, not a real year, and must become None.

    Reviewers correctly flag a stored 0 as invalid placeholder data. Clearing it
    here — before the review phase reads the race — stops that flag from ever
    being raised and costing grade points nothing can resolve.
    """
    race = {
        "candidates": [
            {
                "name": "Candidate",
                "education": [
                    {"institution": "University of Virginia", "degree": "BS", "field": "", "year": 0},
                    {"institution": "Northwestern", "degree": "MBA", "field": "Business", "year": 2011},
                ],
                "career_history": [
                    {"title": "Engineer", "organization": "Acme", "start_year": 0, "end_year": 0},
                ],
            }
        ]
    }

    report = cleanup_race_data(race)

    education = race["candidates"][0]["education"]
    assert education[0]["year"] is None
    assert education[0]["field"] is None
    assert education[1]["year"] == 2011, "a real year must survive untouched"
    career = race["candidates"][0]["career_history"][0]
    assert career["start_year"] is None and career["end_year"] is None
    assert report["placeholder_fields_cleared"] == 4


def test_cleanup_leaves_history_entries_without_placeholders_alone():
    race = {
        "candidates": [
            {
                "name": "Candidate",
                "education": [{"institution": "Harvard", "degree": "JD", "field": "Law", "year": 2002}],
            }
        ]
    }

    report = cleanup_race_data(race)

    assert report["placeholder_fields_cleared"] == 0
    assert race["candidates"][0]["education"][0]["year"] == 2002


def test_cleanup_drops_lineage_entry_citing_a_url_the_pipeline_never_retrieved():
    """A forecast model that invents a plausible source URL must not publish it."""
    race = {
        "polling": [{"source_url": "http://stpetepolls.org/files/CD14_July15.pdf"}],
        "candidates": [
            {
                "name": "Kathy Castor",
                "summary_sources": [{"url": "https://floridapolitics.com/archives/814008-beltran-wins/"}],
            }
        ],
        "forecast": {
            "source_urls": [],
            "evidence_lineage": [
                {
                    "claim": "Castor leads the only general-election poll",
                    "source_url": "https://stpetepolls.org/files/CD14_July15.pdf",
                    "kind": "polling",
                },
                {
                    "claim": "Beltran and Castor are the nominees",
                    "source_url": "https://floridapolitics.com/archives/814008-beltran-wins/",
                    "kind": "race_context",
                },
                {
                    "claim": "The redrawn district leans Republican",
                    "source_url": "https://floridaelevationwatch.gov/LawOffices/USRepresentative",
                    "kind": "race_context",
                },
            ],
        },
    }

    stats = cleanup_race_data(race)
    kept = [item["source_url"] for item in race["forecast"]["evidence_lineage"]]

    assert stats["fabricated_lineage_removed"] == 1
    assert "https://floridaelevationwatch.gov/LawOffices/USRepresentative" not in kept
    # The poll survives despite citing https:// where the stored record used http://.
    assert "https://stpetepolls.org/files/CD14_July15.pdf" in kept
    assert "https://floridapolitics.com/archives/814008-beltran-wins/" in kept


def test_cleanup_keeps_lineage_for_issue_and_roster_sources():
    """Evidence stored anywhere on the race counts as retrieved."""
    race = {
        "candidates": [
            {
                "name": "Mike Beltran",
                "roster_sources": [{"url": "https://ballotpedia.org/Florida_14th_2026"}],
                "issues": {"Economy": {"sources": [{"url": "https://beltranforcongress.com/issues"}]}},
            }
        ],
        "forecast": {
            "source_urls": [],
            "evidence_lineage": [
                {
                    "claim": "Roster confirmed",
                    "source_url": "https://ballotpedia.org/Florida_14th_2026",
                    "kind": "race_context",
                },
                {"claim": "Economic platform", "source_url": "https://beltranforcongress.com/issues", "kind": "race_context"},
            ],
        },
    }

    stats = cleanup_race_data(race)

    assert stats["fabricated_lineage_removed"] == 0
    assert len(race["forecast"]["evidence_lineage"]) == 2
