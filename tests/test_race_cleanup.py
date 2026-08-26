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


def test_cleanup_drops_matchup_naming_only_one_candidate():
    """A primary survey stranded by roster filtering is not a head-to-head."""
    race = {
        # fl-house-09-2026 displayed "Dan Green 12%" from a GOP primary poll.
        "polling": [
            {
                "pollster": "Victory Insights",
                "date": "2026-08-06",
                "matchups": [{"candidates": ["Dan Green"], "percentages": [12.0]}],
                "source_url": "https://news.example/crowded-republican-primary",
            }
        ],
        "forecast": {"based_on_poll_count": 0, "source_urls": [], "evidence_lineage": []},
    }

    stats = cleanup_race_data(race)

    assert stats["incomplete_matchups_removed"] == 1
    assert race["polling"] == []


def test_cleanup_keeps_real_head_to_head_and_drops_only_the_stranded_one():
    """fl-house-14-2026 holds a real general poll beside a primary leftover."""
    race = {
        "polling": [
            {
                "pollster": "St. Pete Polls",
                "date": "2026-07-15",
                "matchups": [
                    {"candidates": ["Mike Beltran", "Kathy Castor"], "percentages": [37.5, 46.2]},
                    {"candidates": ["Mike Beltran"], "percentages": [30.0]},
                ],
                "source_url": "https://stpetepolls.org/files/CD14.pdf",
            },
            {
                "pollster": "Catalyst Research",
                "date": "2026-08-08",
                "matchups": [{"candidates": ["Mike Beltran"], "percentages": [29.5]}],
                "source_url": "https://www.scribd.com/document/1072126270/toplines",
            },
        ],
        "forecast": {"based_on_poll_count": 1, "source_urls": [], "evidence_lineage": []},
    }

    stats = cleanup_race_data(race)

    assert stats["incomplete_matchups_removed"] == 2
    assert len(race["polling"]) == 1
    assert race["polling"][0]["pollster"] == "St. Pete Polls"
    assert race["polling"][0]["matchups"] == [{"candidates": ["Mike Beltran", "Kathy Castor"], "percentages": [37.5, 46.2]}]
    # The surviving general-election poll still backs the forecast.
    assert race["forecast"]["based_on_poll_count"] == 1


def test_cleanup_clamps_poll_count_to_polls_that_actually_remain():
    """fl-house-20-2026 claimed one poll while its rationale said none existed."""
    race = {
        "polling": [
            {
                "pollster": "EMC Research",
                "date": "2026-05-05",
                "matchups": [{"candidates": ["Debbie Wasserman Schultz"], "percentages": [52.0]}],
                "source_url": "https://floridapolitics.com/archives/798629-poll/",
            }
        ],
        "forecast": {"based_on_poll_count": 1, "source_urls": [], "evidence_lineage": []},
    }

    stats = cleanup_race_data(race)

    assert race["polling"] == []
    assert race["forecast"]["based_on_poll_count"] == 0
    assert stats["poll_count_corrections"] == 1


def test_cleanup_leaves_an_honest_poll_count_alone():
    race = {
        "polling": [
            {
                "pollster": "Tavern Research",
                "date": "2026-08-12",
                "matchups": [{"candidates": ["Pia Dandiya", "Casey Askar"], "percentages": [50.0, 50.0]}],
                "source_url": "https://www.nytimes.com/interactive/polls/florida-us-house-22-polls-2026.html",
            }
        ],
        "forecast": {"based_on_poll_count": 1, "source_urls": [], "evidence_lineage": []},
    }

    stats = cleanup_race_data(race)

    assert len(race["polling"]) == 1
    assert race["forecast"]["based_on_poll_count"] == 1
    assert stats["poll_count_corrections"] == 0


_BP_THUMBS = "https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/"


def test_cleanup_clears_ballotpedia_submit_photo_placeholder():
    """ "SubmitPhoto-150px.png" asks for a photo; it is not a photo.

    52 candidates across 46 published races were showing this call-to-action
    graphic as their headshot.
    """
    race = {
        "candidates": [
            {"name": "Jereme Peters", "image_url": _BP_THUMBS + "150/150/SubmitPhoto-150px.png"},
            {"name": "Real Person", "image_url": _BP_THUMBS + "200/300/Real_Person.jpg"},
        ]
    }

    stats = cleanup_race_data(race)

    assert race["candidates"][0]["image_url"] is None
    assert race["candidates"][1]["image_url"] == _BP_THUMBS + "200/300/Real_Person.jpg"
    assert stats["unusable_images_cleared"] == 1


def test_cleanup_keeps_the_candidate_a_shared_photo_is_named_for():
    """One file cannot depict two people, so the one it names keeps it.

    ma-house-04-2026 gave Matthew Cook the file named for Jason Poulos, a rival
    in the same race. It evaded a full-URL duplicate check because the two
    differed only by thumbnail size.
    """
    race = {
        "candidates": [
            {"name": "Jason Poulos", "image_url": _BP_THUMBS + "200/300/Jason_Poulos_2026.jpg"},
            {"name": "Matthew Cook", "image_url": _BP_THUMBS + "100/100/Jason_Poulos_2026.jpg"},
        ]
    }

    stats = cleanup_race_data(race)

    assert race["candidates"][0]["image_url"] == _BP_THUMBS + "200/300/Jason_Poulos_2026.jpg"
    assert race["candidates"][1]["image_url"] is None
    assert stats["unusable_images_cleared"] == 1


def test_cleanup_clears_a_shared_photo_that_names_nobody():
    """With no owner to identify, the file is unusable for either candidate."""
    race = {
        "candidates": [
            {"name": "First Candidate", "image_url": _BP_THUMBS + "200/300/headshot.jpg"},
            {"name": "Second Candidate", "image_url": _BP_THUMBS + "100/100/headshot.jpg"},
        ]
    }

    stats = cleanup_race_data(race)

    assert [c["image_url"] for c in race["candidates"]] == [None, None]
    assert stats["unusable_images_cleared"] == 2


def test_cleanup_leaves_distinct_candidate_photos_alone():
    race = {
        "candidates": [
            {"name": "Warren Davidson", "image_url": _BP_THUMBS + "200/300/Warren_Davidson.jpg"},
            {"name": "Vanessa Enoch", "image_url": "https://example.org/venoch.jpg"},
            {"name": "No Photo", "image_url": None},
        ]
    }

    stats = cleanup_race_data(race)

    assert race["candidates"][0]["image_url"] == _BP_THUMBS + "200/300/Warren_Davidson.jpg"
    assert race["candidates"][1]["image_url"] == "https://example.org/venoch.jpg"
    assert stats["unusable_images_cleared"] == 0


def test_cleanup_corrects_a_primary_date_on_a_general_election_race():
    """The stored date is what a voter reads off the page.

    Three published races held the date of their own primary: 2026-08-04 for
    Michigan and Washington, 2026-06-16 for California. The research agent does
    not reliably fix this from a goal instruction, but it is fully determined --
    a general election is the first Tuesday after the first Monday in November.
    """
    race = {"id": "wa-house-05-2026", "contest_stage": "post_primary_general", "election_date": "2026-08-04"}

    stats = cleanup_race_data(race)

    assert race["election_date"] == "2026-11-03"
    assert stats["election_dates_corrected"] == 1


def test_cleanup_leaves_a_correct_or_pre_primary_date_alone():
    """Only a general-election stage implies the November date."""
    correct = {"id": "x-2026", "contest_stage": "post_primary_general", "election_date": "2026-11-03"}
    assert cleanup_race_data(correct)["election_dates_corrected"] == 0
    assert correct["election_date"] == "2026-11-03"

    # A pre-primary race legitimately carries its primary date.
    pre = {"id": "ma-house-02-2026", "contest_stage": "pre_primary", "election_date": "2026-09-01"}
    assert cleanup_race_data(pre)["election_dates_corrected"] == 0
    assert pre["election_date"] == "2026-09-01"


def test_general_election_day_is_computed_not_hardcoded():
    """First Tuesday after the first Monday in November, for any cycle."""
    from shared.race_cleanup import _general_election_day

    assert _general_election_day(2026) == "2026-11-03"
    assert _general_election_day(2028) == "2028-11-07"
    # 2029: Nov 1 is a Thursday, so the first Monday is the 5th and the day is the 6th.
    assert _general_election_day(2029) == "2029-11-06"


def test_wix_placeholder_thumbnails_are_upgraded_to_full_size():
    """Wix serves a blurred 41x54 placeholder from the real photo's URL space."""
    race = {
        "candidates": [
            {
                "name": "Jonathan Jackson",
                "image_url": (
                    "https://static.wixstatic.com/media/5ffdcf_6eb4f626c8fa442c8418d07553e6b439~mv2.png"
                    "/v1/crop/x_114,y_72,w_830,h_1106/fill/w_41,h_54,al_c,q_85,blur_2/1723248559532.png"
                ),
            }
        ]
    }

    result = cleanup_race_data(race)

    assert result["wix_thumbnails_upgraded"] == 1
    assert race["candidates"][0]["image_url"] == (
        "https://static.wixstatic.com/media/5ffdcf_6eb4f626c8fa442c8418d07553e6b439~mv2.png"
    )


def test_wix_urls_without_a_transform_are_left_alone():
    url = "https://static.wixstatic.com/media/ddc900_b203b52ea1384bc68cfb710790e19750~mv2.png"
    race = {"candidates": [{"name": "A", "image_url": url}]}

    result = cleanup_race_data(race)

    assert result["wix_thumbnails_upgraded"] == 0
    assert race["candidates"][0]["image_url"] == url


def test_legitimate_wix_transforms_are_left_alone():
    ordinary_crop = (
        "https://static.wixstatic.com/media/photo~mv2.jpg"
        "/v1/crop/x_10,y_20,w_1200,h_1500/fill/w_800,h_1000,al_c,q_90/photo.jpg"
    )
    large_blurred_render = (
        "https://static.wixstatic.com/media/photo~mv2.jpg" "/v1/fill/w_1200,h_1500,al_c,q_90,blur_2/photo.jpg"
    )
    race = {
        "candidates": [
            {"name": "A", "image_url": ordinary_crop},
            {"name": "B", "image_url": large_blurred_render},
        ]
    }

    result = cleanup_race_data(race)

    assert result["wix_thumbnails_upgraded"] == 0
    assert race["candidates"][0]["image_url"] == ordinary_crop
    assert race["candidates"][1]["image_url"] == large_blurred_render


def test_non_wix_images_are_left_alone():
    url = "https://example.com/media/photo.jpg/v1/fill/w_41,h_54/photo.jpg"
    race = {"candidates": [{"name": "A", "image_url": url}, {"name": "B", "image_url": None}]}

    result = cleanup_race_data(race)

    assert result["wix_thumbnails_upgraded"] == 0
    assert race["candidates"][0]["image_url"] == url
