"""Tests for pipeline agent prompt templates and formatting."""

from pipeline_client.agent.prompts import (
    CANONICAL_ISSUES,
    DISCOVERY_SYSTEM,
    DISCOVERY_USER,
    FINANCE_VOTING_USER,
    FORECAST_SYSTEM,
    FORECAST_USER,
    ISSUE_SUBAGENT_SYSTEM,
    ISSUE_SUBAGENT_USER,
    ITERATE_USER,
    REFINE_SYSTEM,
    REFINE_USER,
    ROSTER_SYNC_SYSTEM,
    ROSTER_SYNC_USER,
    UPDATE_ISSUE_SUBAGENT_SYSTEM,
    UPDATE_ISSUE_SUBAGENT_USER,
    UPDATE_META_SYSTEM,
    UPDATE_META_USER,
)
from shared.models import LEGACY_ISSUE_NAMES

# ---------------------------------------------------------------------------
# Canonical issues
# ---------------------------------------------------------------------------


def test_canonical_issues_count():
    """All canonical issues are defined."""
    assert len(CANONICAL_ISSUES) == 12


def test_canonical_issues_no_duplicates():
    """No duplicate canonical issues."""
    assert len(CANONICAL_ISSUES) == len(set(CANONICAL_ISSUES))


def test_canonical_issues_thematic_order():
    """Canonical issues are in the expected thematic order."""
    assert CANONICAL_ISSUES[0] == "Healthcare"
    assert CANONICAL_ISSUES[-1] == "Local Issues"


def test_agent_prompts_do_not_request_legacy_issue_names():
    """Agent-facing issue lists use canonical names only; legacy migration stays in schemas."""
    prompt_text = "\n".join(
        [
            ", ".join(CANONICAL_ISSUES),
            DISCOVERY_USER,
            REFINE_USER,
            UPDATE_META_USER,
            ISSUE_SUBAGENT_USER,
            UPDATE_ISSUE_SUBAGENT_USER,
            ITERATE_USER,
        ]
    )
    for legacy_issue in LEGACY_ISSUE_NAMES:
        assert legacy_issue not in CANONICAL_ISSUES
        assert legacy_issue not in prompt_text


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------


def test_discovery_user_formats():
    """Discovery user prompt accepts race_id."""
    result = DISCOVERY_USER.format(race_id="mo-senate-2024")
    assert "mo-senate-2024" in result


def test_issue_subagent_user_formats():
    """Issue subagent user prompt accepts all required variables."""
    result = ISSUE_SUBAGENT_USER.format(
        race_id="mo-senate-2024",
        candidate_name="Alice",
        issue="Healthcare",
        handoff_context="No prior context available.",
        candidate_website="https://alice.example.com",
        candidate_issue_urls="(none found)",
    )
    assert "mo-senate-2024" in result
    assert "Alice" in result
    assert "Healthcare" in result


def test_refine_user_formats():
    """Refine user prompt accepts race_id, candidate_name, candidate_json, and other params."""
    result = REFINE_USER.format(
        race_id="mo-senate-2024",
        candidate_name="Jane Doe",
        candidate_website="https://janedoe.com",
        candidate_issue_urls="https://janedoe.com/issues, https://janedoe.com/platform",
        candidate_json='{"name": "Jane Doe"}',
        race_description="A senate race.",
        other_candidates="John Smith",
        all_issues="Healthcare, Economy",
    )
    assert "mo-senate-2024" in result
    assert "Jane Doe" in result
    assert "Healthcare, Economy" in result
    assert "https://janedoe.com/issues" in result


def test_update_meta_user_formats():
    """Update meta prompt accepts race_id, candidate_names, and last_updated."""
    result = UPDATE_META_USER.format(
        race_id="mo-senate-2024",
        candidate_names="Alice, Bob",
        last_updated="2024-01-01T00:00:00Z",
        current_date="2026-06-14",
    )
    assert "mo-senate-2024" in result
    assert "2024-01-01" in result


def test_iterate_user_formats():
    """Iterate prompt accepts candidate source hints and review flags."""
    result = ITERATE_USER.format(
        race_id="mo-senate-2024",
        candidate_name="Jane Doe",
        candidate_website="https://janedoe.com",
        candidate_issue_urls="https://janedoe.com/issues, https://janedoe.com/platform",
        candidate_json='{"name": "Jane Doe"}',
        review_flags="[WARNING] issues.Healthcare: weak sourcing",
        all_issues="Healthcare, Economy",
    )
    assert "mo-senate-2024" in result
    assert "Jane Doe" in result
    assert "https://janedoe.com/issues" in result
    assert "weak sourcing" in result


def test_roster_sync_prompt_formats():
    """Roster sync prompt accepts race_id, last_updated, candidate_names."""
    result = ROSTER_SYNC_USER.format(
        race_id="ga-senate-2026",
        last_updated="2025-01-01T00:00:00Z",
        current_date="2026-06-14",
        candidate_names="Alice, Bob",
    )
    assert "ga-senate-2026" in result
    assert "Alice, Bob" in result
    assert "add_candidate" in result


def test_issue_subagent_prompt_formats():
    """Issue sub-agent prompt accepts required variables."""
    result = ISSUE_SUBAGENT_USER.format(
        candidate_name="Jane Doe",
        race_id="mi-senate-2026",
        issue="Healthcare",
        candidate_website="https://example.com/",
        candidate_issue_urls="https://example.com/issues",
        handoff_context="No prior context available.",
    )
    assert "Jane Doe" in result
    assert "Healthcare" in result
    assert "https://example.com/issues" in result
    assert "set_issue_stance" in result


def test_update_issue_subagent_prompt_formats():
    """Update issue sub-agent prompt accepts required variables."""
    result = UPDATE_ISSUE_SUBAGENT_USER.format(
        candidate_name="Jane Doe",
        race_id="mi-senate-2026",
        issue="Healthcare",
        last_updated="2025-01-01T00:00:00Z",
        existing_stance="  Stance: Supports ACA.\n  Confidence: high",
        candidate_website="https://example.com/",
        candidate_issue_urls="https://example.com/issues",
        handoff_context="No prior context available.",
    )
    assert "Jane Doe" in result
    assert "Healthcare" in result
    assert "Supports ACA" in result
    assert "https://example.com/issues" in result


# ---------------------------------------------------------------------------
# Prompt content checks
# ---------------------------------------------------------------------------


def test_discovery_prompt_mentions_donor_sources():
    """Discovery prompt tells the model to include donor summary and links."""
    result = DISCOVERY_USER.format(race_id="mo-senate-2024")
    assert "donor_summary" in result
    assert "donor_sources" in result
    assert "links" in result


def test_refine_prompt_mentions_donor_sources():
    """Refine prompt asks agent to fill donor_summary using set_donor_summary."""
    result = REFINE_USER.format(
        race_id="mo-senate-2024",
        candidate_name="Jane Doe",
        candidate_website="https://janedoe.com",
        candidate_issue_urls="https://janedoe.com/issues",
        candidate_json='{"name": "Jane Doe"}',
        race_description="A senate race.",
        other_candidates="John Smith",
        all_issues="Healthcare, Economy",
    )
    assert "set_donor_summary" in result
    assert "donor_sources" in ITERATE_USER


def test_update_prompt_mentions_donor_sources():
    """Update meta prompt uses donor_summary instead of top_donors."""
    result = UPDATE_META_USER.format(
        race_id="mo-senate-2024",
        candidate_names="Alice, Bob",
        last_updated="2024-01-01T00:00:00Z",
        current_date="2026-06-14",
    )
    assert "donor_summary" in result
    assert "donor_sources" in FINANCE_VOTING_USER
    assert 'Do NOT put "Sources:"' in FINANCE_VOTING_USER
    assert "top_donors" not in result


def test_prompts_contain_rules():
    """All system prompts include shared rules."""
    for prompt in [DISCOVERY_SYSTEM, ISSUE_SUBAGENT_SYSTEM, REFINE_SYSTEM, UPDATE_META_SYSTEM, UPDATE_ISSUE_SUBAGENT_SYSTEM]:
        assert "nonpartisan" in prompt.lower()
        assert "web_search" in prompt


def test_prompts_mention_confidence_levels():
    """All system prompts describe the confidence levels."""
    for prompt in [DISCOVERY_SYSTEM, ISSUE_SUBAGENT_SYSTEM, REFINE_SYSTEM, UPDATE_META_SYSTEM, UPDATE_ISSUE_SUBAGENT_SYSTEM]:
        assert "high" in prompt.lower()
        assert "medium" in prompt.lower()
        assert "low" in prompt.lower()


def test_roster_sync_system_restricts_to_roster_tools_only():
    """Roster sync prompt explicitly restricts edits to roster tools."""
    assert "add_candidate" in ROSTER_SYNC_SYSTEM
    assert "remove_candidate" in ROSTER_SYNC_SYSTEM
    assert "rename_candidate" in ROSTER_SYNC_SYSTEM
    assert "Do NOT call any non-roster editing tools" in ROSTER_SYNC_SYSTEM


def test_discovery_prompts_exclude_defeated_primary_candidates():
    """General-election rosters must remove candidates who lost completed primaries."""
    assert "Do NOT include defeated primary candidates" in DISCOVERY_USER
    assert "verifiably lost a completed" in ROSTER_SYNC_SYSTEM
    assert "lost a completed primary" in ROSTER_SYNC_USER


def test_iterate_prompt_allows_candidate_removal_for_invalid_roster_entries():
    """Iteration prompt allows removing clearly invalid candidates with evidence."""
    assert "CANDIDATE VALIDITY / ROSTER flags" in ITERATE_USER
    assert "remove_candidate" in ITERATE_USER
    assert "Do NOT remove a candidate solely due to sparse issue data" in ITERATE_USER


def test_review_prompt_exists():
    """Review prompts are defined and contain expected content."""
    from pipeline_client.agent.prompts import REVIEW_SYSTEM, REVIEW_USER

    assert "fact-checking" in REVIEW_SYSTEM.lower()
    assert "{race_id}" in REVIEW_USER
    assert "{profile_json}" in REVIEW_USER
    assert "{change_manifest}" in REVIEW_USER
    assert "verdict" in REVIEW_USER


def test_discovery_prompt_asks_for_career():
    """Discovery prompt includes career history request."""
    assert "career" in DISCOVERY_USER.lower()
    assert "career_history" in DISCOVERY_USER


def test_discovery_prompt_asks_for_education():
    """Discovery prompt includes education request."""
    assert "education" in DISCOVERY_USER.lower()


def test_discovery_prompt_asks_for_image():
    """Discovery prompt includes image/headshot request."""
    assert "image_url" in DISCOVERY_USER or "photo" in DISCOVERY_USER.lower()


def test_refine_prompt_asks_for_image():
    """Refine prompt includes image filling."""
    assert "image_url" in REFINE_USER or "headshot" in REFINE_USER.lower()


def test_routine_prompts_leave_polling_and_voter_resources_to_standalone_steps():
    from pipeline_client.agent.prompts import REFINE_META_USER, UPDATE_META_USER

    assert "Recent polls" not in DISCOVERY_USER
    assert "add_poll" not in REFINE_META_USER
    assert "register_to_vote_url" not in REFINE_META_USER
    assert "add_poll" not in UPDATE_META_USER
    assert "register_to_vote_url" not in UPDATE_META_USER


def test_iteration_retains_polling_and_voter_resource_repair_access():
    from pipeline_client.agent.prompts import ITERATE_META_USER

    assert "remove_poll" in ITERATE_META_USER
    assert "ballotpedia_url" in ITERATE_META_USER


def test_polling_prompt_distinguishes_source_only_polls_from_numeric_matchups():
    from pipeline_client.agent.prompts import POLLING_USER

    assert "matchups: []" in POLLING_USER
    assert "does not publish numeric candidate percentages" in POLLING_USER


def test_forecast_prompt_formats_and_disallows_search():
    result = FORECAST_USER.format(
        race_id="ga-senate-2026",
        current_date="2026-06-20",
        office="United States Senate",
        jurisdiction="Georgia",
        state="Georgia",
        district="",
        description="A competitive Senate race.",
        candidates_json='[{"name":"Alice","party":"Democratic"}]',
        polling_note="No public polling found.",
        polling_json="[]",
        market_signals_json="[]",
        forecast_json="null",
    )

    assert "ga-senate-2026" in result
    assert "set a forecast" in result.lower()
    assert "Prediction market signals" in result
    assert "Do not search the web" in FORECAST_SYSTEM
    assert "Use set_forecast exactly once" in FORECAST_SYSTEM
