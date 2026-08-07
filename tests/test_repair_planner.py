from shared import repair_planner
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
    stages = [group["stage"] for group in plan["repair_groups"]]
    assert stages == ["roster", "candidate", "candidate", "finalization"]
    assert plan["repair_groups"][0]["candidate_names"] is None
    assert {tuple(group["candidate_names"] or []) for group in plan["repair_groups"] if group["stage"] == "candidate"} == {
        ("Alice",),
        ("Bob",),
    }
    # The validation tail is guaranteed for the plan, not repeated per group.
    assert plan["repair_groups"][-1]["enabled_steps"][-2:] == ["review", "iteration"]
    for group in plan["repair_groups"]:
        if group["stage"] == "candidate":
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


def test_validation_tail_is_planned_once_not_per_candidate():
    """Regression: every candidate group used to carry the race-wide tail.

    A three-candidate repair therefore ran review and iteration three times,
    each pass grading a race the later passes had not finished, and the cost
    ceiling multiplied accordingly.
    """
    race = {
        "candidates": [
            {"name": "Alice", "issues": {}},
            {"name": "Bob", "issues": {}},
            {"name": "Carla", "issues": {}},
        ],
        "forecast": None,
    }

    plan = build_repair_plan("ne-house-02-2026", race, freshness="stale")

    tail = {"review", "iteration", "polling", "forecast", "voter_resources"}
    candidate_groups = [group for group in plan["repair_groups"] if group["stage"] == "candidate"]
    assert len(candidate_groups) == 3
    for group in candidate_groups:
        assert not tail & set(group["enabled_steps"]), f"candidate group leaked race-wide steps: {group['enabled_steps']}"

    finalization = [group for group in plan["repair_groups"] if group["stage"] == "finalization"]
    assert len(finalization) == 1
    assert "review" in finalization[0]["enabled_steps"]
    assert "iteration" in finalization[0]["enabled_steps"]


def test_repair_groups_are_returned_in_queue_order():
    race = {
        "candidates": [{"name": "Alice", "issues": {}}],
        "forecast": None,
    }

    plan = build_repair_plan("ne-house-02-2026", race, freshness="stale")
    stages = [group["stage"] for group in plan["repair_groups"]]

    assert stages.index("roster") < stages.index("candidate") < stages.index("finalization")


def test_issue_research_still_guarantees_a_validation_tail():
    """The 'never queue issues alone' invariant must survive the split."""
    race = {"candidates": [{"name": "Alice", "issues": {}}], "forecast": None}

    plan = build_repair_plan("ne-house-02-2026", race)

    assert "issues" in plan["recommended_steps"]
    all_steps = {step for group in plan["repair_groups"] for step in group["enabled_steps"]}
    assert {"review", "iteration"} <= all_steps


# ---------------------------------------------------------------------------
# The issue-research tail is spelled out in more than one place
# ---------------------------------------------------------------------------


def test_issue_research_steps_are_all_real_pipeline_steps():
    """A typo here does not raise — the step simply never gets planned."""
    from shared.pipeline_config import PIPELINE_STEP_IDS

    assert repair_planner._ISSUE_RESEARCH_CANDIDATE_STEPS <= PIPELINE_STEP_IDS
    assert repair_planner._ISSUE_RESEARCH_FINALIZATION_STEPS <= PIPELINE_STEP_IDS


def test_safety_steps_are_exactly_the_two_halves():
    """Guards the split itself: a step added to neither half would vanish from
    the safety set while still looking accounted for."""
    assert repair_planner._ISSUE_RESEARCH_SAFETY_STEPS == (
        repair_planner._ISSUE_RESEARCH_CANDIDATE_STEPS | repair_planner._ISSUE_RESEARCH_FINALIZATION_STEPS
    )
    assert not (repair_planner._ISSUE_RESEARCH_CANDIDATE_STEPS & repair_planner._ISSUE_RESEARCH_FINALIZATION_STEPS)


def test_issue_research_never_plans_without_its_validation_tail():
    """Raw issue stances are unvalidated until review and iteration run, which is
    why the planner folds the tail into any plan that researches issues. If
    review or iteration ever left the finalization half, the planner would start
    producing exactly the issues-only run the pipeline forbids."""
    assert {"review", "iteration"} <= repair_planner._ISSUE_RESEARCH_FINALIZATION_STEPS
    assert "issues" in repair_planner._ISSUE_RESEARCH_CANDIDATE_STEPS


def test_triage_queues_the_same_combined_run_the_planner_plans():
    """`scripts/triage_race_issues.py` queues COMBINED_STEPS; the planner builds
    its own set. They are the same combined run described in CLAUDE.md, written
    down twice, and a race repaired by one route should not get a different set
    of steps than the other."""
    from scripts.triage_race_issues import COMBINED_STEPS

    assert set(COMBINED_STEPS) == repair_planner._ISSUE_RESEARCH_SAFETY_STEPS


def test_the_combined_run_deliberately_omits_roster_and_asset_work():
    """discovery settles the roster and images fetches headshots; neither is
    issue research, and discovery in particular has to have run *before* this
    work rather than alongside it."""
    from shared.pipeline_config import PIPELINE_STEP_IDS

    assert PIPELINE_STEP_IDS - repair_planner._ISSUE_RESEARCH_SAFETY_STEPS == {"discovery", "images"}
