from shared.models import CanonicalIssue
from shared.repair_planner import build_repair_plan, summarize_repair_plans


def test_discovery_race_plan_targets_missing_research_with_conservative_ceiling():
    race = {
        "candidates": [
            {"name": "Alice", "image_url": None, "issues": {}},
            {"name": "Bob", "image_url": "https://example.com/bob.jpg", "issues": {}},
        ],
        "forecast": None,
    }

    plan = build_repair_plan("ca-house-01-2026", race)

    assert plan["needs_repair"] is True
    assert plan["research_tier"] == "discovery_only"
    assert plan["recommended_steps"] == [
        "discovery",
        "images",
        "issues",
        "finance",
        "refinement",
        "polling",
        "forecast",
        "voter_resources",
        "review",
        "iteration",
    ]
    assert plan["candidate_names"] == ["Alice", "Bob"]
    assert plan["estimated_max_cost_usd"] > 1
    assert plan["estimated_max_search_calls"] >= 240
    assert plan["estimate_kind"] == "static_ceiling"
    assert plan["repair_groups"][0]["candidate_names"] is None
    assert {tuple(group["candidate_names"] or []) for group in plan["repair_groups"][1:]} == {
        ("Alice",),
        ("Bob",),
    }
    for group in plan["repair_groups"][1:]:
        assert group["enabled_steps"][-2:] == ["review", "iteration"]
        assert "issues" in group["enabled_steps"]


def test_validated_complete_race_needs_no_repair():
    issues = {
        issue.value: {
            "stance": "Supports a documented policy.",
            "sources": [{"url": f"https://example.com/{index}"}],
        }
        for index, issue in enumerate(CanonicalIssue)
    }
    race = {
        "candidates": [
            {
                "name": "Alice",
                "image_url": "https://example.com/alice.jpg",
                "roster_sources": [{"url": "https://elections.example.gov"}],
                "issues": issues,
                "donor_summary": "Reported receipts.",
                "donor_source_url": "https://fec.gov",
            }
        ],
        "forecast": {"rating": "safe_d", "source_urls": ["https://example.com/forecast"]},
        "validation_grade": {"grade": "A", "passed": True},
    }

    plan = build_repair_plan("ca-house-02-2026", race)

    assert plan["needs_repair"] is False
    assert plan["recommended_steps"] == []
    assert plan["candidate_names"] is None
    assert plan["estimated_max_cost_usd"] == 0


def test_low_grade_plan_requires_review_and_iteration():
    race = {
        "candidates": [{"name": "Alice", "roster_sources": [{"url": "https://example.gov"}]}],
        "validation_grade": {"grade": "C", "passed": False},
    }

    plan = build_repair_plan("ca-house-03-2026", race)

    assert "review" in plan["recommended_steps"]
    assert "iteration" in plan["recommended_steps"]


def test_summarize_repair_plans_rolls_up_ceilings():
    summary = summarize_repair_plans(
        [
            {"needs_repair": True, "estimated_max_cost_usd": 1.25, "estimated_max_search_calls": 20},
            {"needs_repair": False, "estimated_max_cost_usd": 0, "estimated_max_search_calls": 0},
        ]
    )

    assert summary == {
        "plans": [
            {"needs_repair": True, "estimated_max_cost_usd": 1.25, "estimated_max_search_calls": 20},
            {"needs_repair": False, "estimated_max_cost_usd": 0, "estimated_max_search_calls": 0},
        ],
        "race_count": 2,
        "repair_count": 1,
        "estimated_max_cost_usd": 1.25,
        "estimated_max_search_calls": 20,
    }
