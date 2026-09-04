"""Inherited source timestamps must be repaired, not just newly written ones."""

from pipeline_client.agent.agent import _sanitize_source_last_accessed


def test_repairs_the_retrieval_status_value_copied_into_last_accessed():
    """tx-house-05 carried `last_accessed: "content"` through four runs.

    #350 and #361 fixed the two write paths, but `add_candidate` deliberately
    reuses persisted source dicts so evidence survives a re-run — so a value
    poisoned once was inherited verbatim and the race could never self-heal.
    """
    race = {
        "candidates": [
            {
                "name": "Chelsey Hockett",
                "roster_sources": [
                    {"url": "https://example.com/a", "last_accessed": "content", "retrieval_status": "content"},
                ],
            }
        ]
    }

    _sanitize_source_last_accessed(race)

    repaired = race["candidates"][0]["roster_sources"][0]["last_accessed"]
    assert repaired != "content"
    assert repaired.startswith("20")


def test_preserves_a_valid_timestamp_and_prefers_retrieved_as_the_fallback():
    race = {
        "candidates": [
            {
                "roster_sources": [
                    {"url": "https://example.com/good", "last_accessed": "2026-08-29T16:12:06.048587Z"},
                    {"url": "https://example.com/blank", "last_accessed": "", "retrieved": "2026-08-01T00:00:00Z"},
                    {"url": "https://example.com/null", "last_accessed": None},
                ]
            }
        ]
    }

    _sanitize_source_last_accessed(race)
    sources = race["candidates"][0]["roster_sources"]

    assert sources[0]["last_accessed"] == "2026-08-29T16:12:06.048587Z"
    assert sources[1]["last_accessed"] == "2026-08-01T00:00:00Z"
    assert sources[2]["last_accessed"] and sources[2]["last_accessed"].startswith("20")


def test_reaches_every_source_list_in_the_document():
    """Sources hide in summary_sources, voting_sources, polling, reviews and more."""
    race = {
        "candidates": [
            {"summary_sources": [{"url": "https://example.com/s", "last_accessed": "content"}]},
            {"voting_sources": [{"url": "https://example.com/v", "last_accessed": "not a date"}]},
        ],
        "polling": [{"sources": [{"url": "https://example.com/p", "last_accessed": "nope"}]}],
    }

    _sanitize_source_last_accessed(race)

    assert race["candidates"][0]["summary_sources"][0]["last_accessed"].startswith("20")
    assert race["candidates"][1]["voting_sources"][0]["last_accessed"].startswith("20")
    assert race["polling"][0]["sources"][0]["last_accessed"].startswith("20")


def test_leaves_dicts_without_a_url_alone():
    """Only source-shaped objects carry last_accessed; don't rewrite anything else."""
    race = {"agent_metrics": {"last_accessed": "content"}}

    _sanitize_source_last_accessed(race)

    assert race["agent_metrics"]["last_accessed"] == "content"
