"""The roster-evidence contract must mean the same thing to the prompt and the tool.

These tests exist because the two used to disagree. On ne-house-02-2026 the
prompt told the model a Ballotpedia race page was acceptable completeness
evidence, ``finalize_roster`` rejected it, and the model spent its entire
iteration budget unable to reconcile the instruction with the error. Anything
here that fails means that class of bug is back.
"""

import pytest

from pipeline_client.agent import handlers
from pipeline_client.agent.prompts import DISCOVERY_USER, ROSTER_SYNC_USER, cycle_kwargs
from pipeline_client.agent.roster import ROSTER_CAP
from pipeline_client.agent.roster_contract import (
    AUTHORITATIVE_SOURCE_CLASSES,
    COMPLETENESS_SOURCE_CLASSES,
    COMPLETENESS_TIERS,
    CONTEST_STAGES,
    MEMBERSHIP_TIERS,
    QUALIFYING_SOURCE_CLASSES,
    ROSTER_LISTING_SOURCE_CLASSES,
    SOURCE_CLASSES,
    lacks_tier3_corroboration,
    tier_rejection_reason,
)
from pipeline_client.agent.tools import (
    ADD_CANDIDATE_TOOL,
    CONTEST_STAGE_VALUES,
    FINALIZE_ROSTER_TOOL,
    REMOVE_CANDIDATE_TOOL,
    SET_CANDIDATE_ROSTER_SOURCES_TOOL,
)
from shared.models import ContestStage


def test_prompt_carries_no_unsubstituted_slots():
    assert "@@" not in ROSTER_SYNC_USER


def test_prompt_still_formats_with_runtime_placeholders():
    """Rendering the contract must not consume the caller's format placeholders."""
    rendered = ROSTER_SYNC_USER.format(
        **cycle_kwargs("ne-house-02-2026"),
        race_id="ne-house-02-2026",
        last_updated="2026-07-01",
        current_date="2026-08-02",
        candidate_names="A, B",
        race_description="desc",
    )
    assert "ne-house-02-2026" in rendered
    # Rendered contract text must not smuggle in brace syntax of its own; a stray
    # "{" here means a future edit will crash .format() at run time, not in CI.
    assert "{" not in rendered and "}" not in rendered


@pytest.mark.parametrize("source_class", sorted(QUALIFYING_SOURCE_CLASSES))
def test_prompt_names_every_class_the_tool_accepts(source_class):
    """A class the tool honours but the prompt never mentions is unreachable."""
    assert source_class in ROSTER_SYNC_USER.casefold()


def test_prompt_states_the_cap_the_tool_enforces():
    assert str(ROSTER_CAP) in ROSTER_SYNC_USER


@pytest.mark.parametrize("tier", [tier.tier for tier in MEMBERSHIP_TIERS])
def test_prompt_describes_every_evidence_tier(tier):
    assert f"Tier {tier}" in ROSTER_SYNC_USER


def test_completeness_classes_are_a_subset_of_qualifying_classes():
    """Completeness evidence is a stricter case of roster evidence, never a looser one."""
    assert COMPLETENESS_SOURCE_CLASSES <= QUALIFYING_SOURCE_CLASSES
    assert ROSTER_LISTING_SOURCE_CLASSES <= QUALIFYING_SOURCE_CLASSES
    assert AUTHORITATIVE_SOURCE_CLASSES <= QUALIFYING_SOURCE_CLASSES
    assert "other" not in QUALIFYING_SOURCE_CLASSES
    assert "other" in SOURCE_CLASSES


def test_ballotpedia_race_page_is_accepted_completeness_evidence():
    """The ne-house-02-2026 regression: the prompt promises this, so the tool must honour it."""
    assert "ballotpedia" in COMPLETENESS_SOURCE_CLASSES
    assert "Ballotpedia" in ROSTER_SYNC_USER


def test_campaign_site_cannot_prove_a_candidate_is_absent_from_a_field():
    """A campaign site speaks for one candidate and never enumerates opponents."""
    assert "campaign" not in ROSTER_LISTING_SOURCE_CLASSES
    assert "campaign" in QUALIFYING_SOURCE_CLASSES


# --- tier grading: behaviour must match the inline logic this replaced ---------


@pytest.mark.parametrize(
    "tier,status,source_type,expected_ok",
    [
        (1, "content", "official", True),
        (1, "content", "fec", True),
        (1, "content", "news", False),  # tier 1 is authoritative-only
        (1, "snippet", "official", False),  # tier 1 needs retrieved content
        (2, "content", "campaign", True),
        (2, "content", "ballotpedia", True),
        (2, "content", "news", True),
        (2, "content", "official", False),  # official content is tier 1, not 2
        (2, "snippet", "news", False),
        (3, "snippet", "news", True),
        (3, "snippet", "official", True),
        (3, "content", "news", False),  # retrieved content is not a snippet
        (4, "content", "official", False),  # unrecognized grade
        (None, None, "official", False),
    ],
)
def test_tier_grading(tier, status, source_type, expected_ok):
    source = {"evidence_tier": tier, "retrieval_status": status, "type": source_type}
    assert (tier_rejection_reason(source) is None) is expected_ok


def test_tier_rejection_reasons_are_specific():
    """Callers surface these verbatim; a generic message sends the model source-hunting."""
    reason = tier_rejection_reason({"evidence_tier": 1, "retrieval_status": "snippet", "type": "official"})
    assert reason and "tier 1" in reason
    unknown = tier_rejection_reason({"evidence_tier": 9, "retrieval_status": "content", "type": "official"})
    assert unknown and "not a recognized evidence grade" in unknown


# --- tier-3 corroboration -----------------------------------------------------


def _snippet(url, source_type="news"):
    return {"evidence_tier": 3, "retrieval_status": "snippet", "type": source_type, "url": url}


def test_single_domain_snippets_lack_corroboration():
    assert lacks_tier3_corroboration([_snippet("https://a.com/1"), _snippet("https://a.com/2")])


def test_two_independent_domains_corroborate():
    assert not lacks_tier3_corroboration([_snippet("https://a.com/1"), _snippet("https://b.com/2")])


def test_authoritative_snippet_waives_corroboration():
    assert not lacks_tier3_corroboration([_snippet("https://sos.ga.gov/x", "official")])


def test_corroboration_does_not_apply_when_higher_tier_evidence_exists():
    mixed = [
        _snippet("https://a.com/1"),
        {"evidence_tier": 1, "retrieval_status": "content", "type": "official", "url": "https://a.com/2"},
    ]
    assert not lacks_tier3_corroboration(mixed)


def test_empty_source_list_is_not_a_corroboration_failure():
    """No sources is a different rejection, reported elsewhere with its own reason."""
    assert not lacks_tier3_corroboration([])


# --- the handler must read the contract, not a private copy -------------------


def test_handler_constants_are_the_contract_objects():
    """Guards against someone reintroducing a local literal set in handlers."""
    assert handlers._QUALIFYING_ROSTER_SOURCE_TYPES is QUALIFYING_SOURCE_CLASSES
    assert handlers._ROSTER_SOURCE_TYPES is SOURCE_CLASSES


def test_completeness_tiers_exclude_snippets():
    """A snippet of a list page is indistinguishable from a truncated one."""
    snippet_tiers = {tier.tier for tier in MEMBERSHIP_TIERS if tier.retrieval_status == "snippet"}
    assert not (COMPLETENESS_TIERS & snippet_tiers)


# --- removal grounds: stated once, asserted in three places -------------------


def test_prompt_and_handler_state_the_same_removal_grounds():
    """The prompt instructs, the tool refuses, and the adjudicator judges — all
    from REMOVAL_GROUNDS. Three hand-written copies is how they drifted before."""
    from pipeline_client.agent.roster_contract import REMOVAL_GROUNDS, removal_grounds_sentence

    rendered = ROSTER_SYNC_USER.casefold()
    for ground in REMOVAL_GROUNDS:
        assert ground.casefold() in rendered, f"prompt omits removal ground: {ground!r}"

    sentence = removal_grounds_sentence().casefold()
    for ground in REMOVAL_GROUNDS:
        assert ground.casefold() in sentence


def test_removal_grounds_are_not_empty():
    """Guards against the assertions above passing vacuously."""
    from pipeline_client.agent.roster_contract import REMOVAL_GROUNDS

    assert len(REMOVAL_GROUNDS) >= 3


def test_adjudicator_withdrawal_question_covers_the_same_grounds():
    """The judge must be asked about the grounds the caller was told to cite."""
    from pipeline_client.agent.roster_adjudicator import _CLAIM_QUESTIONS, Claim

    question = _CLAIM_QUESTIONS[Claim.WITHDRAWAL].casefold()
    for keyword in ("withdraw", "disqualified", "primary", "former officeholder"):
        assert keyword in question, f"withdrawal question omits {keyword!r}"


# ---------------------------------------------------------------------------
# Contest stages
# ---------------------------------------------------------------------------


def test_every_contest_stage_reaches_validator_schema_and_prompt():
    """A stage the model is never shown is a stage it can never emit.

    The stage list is consumed in four places: the ContestStage enum, the
    handler's validator (CONTEST_STAGES), the tool schema the model is given
    (CONTEST_STAGE_VALUES) and the JSON shape spelled out in DISCOVERY_USER.
    They were four hand-written copies. Adding a stage for a state whose rules
    need one — a Louisiana-style all-party primary, say — had to land in all
    four, and missing the schema or the prompt fails silently: the tool accepts
    a value the model is never told exists.
    """
    canonical = [stage.value for stage in ContestStage]

    assert CONTEST_STAGES == frozenset(canonical)
    assert CONTEST_STAGE_VALUES == canonical, "tool schema must offer the stages in enum order"
    assert "|".join(canonical) in DISCOVERY_USER
    assert "@@CONTEST_STAGES@@" not in DISCOVERY_USER, "stage token was never substituted"


# ---------------------------------------------------------------------------
# Tool schemas must promise only what the handler accepts
# ---------------------------------------------------------------------------


def _schema_enums(node, field):
    """Every `enum` list declared for `field` anywhere inside a tool schema."""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == field and isinstance(value, dict) and "enum" in value:
                found.append(tuple(value["enum"]))
            found.extend(_schema_enums(value, field))
    elif isinstance(node, list):
        for item in node:
            found.extend(_schema_enums(item, field))
    return found


ROSTER_SOURCE_TOOLS = [ADD_CANDIDATE_TOOL, REMOVE_CANDIDATE_TOOL, SET_CANDIDATE_ROSTER_SOURCES_TOOL]


@pytest.mark.parametrize("tool", ROSTER_SOURCE_TOOLS, ids=lambda t: t["function"]["name"])
def test_source_type_schema_offers_only_classes_that_can_qualify(tool):
    """`other` used to be offered by add_candidate and set_candidate_roster_sources.

    It is the one class that can never carry roster evidence — the rendered
    contract says so outright — and `_roster_source_rejection_reason` refuses it.
    Offering it costs an iteration: the model picks the value the schema told it
    was legal, the call fails, and it has to guess what to send instead. This is
    the same prompt-promises-what-the-tool-rejects bug this module exists to stop.
    """
    for enum_values in _schema_enums(tool, "type"):
        assert set(enum_values) == QUALIFYING_SOURCE_CLASSES
        assert "other" not in enum_values


@pytest.mark.parametrize(
    "tool",
    ROSTER_SOURCE_TOOLS + [FINALIZE_ROSTER_TOOL],
    ids=lambda t: t["function"]["name"],
)
def test_retrieval_status_schema_matches_the_graded_values(tool):
    graded = {tier.retrieval_status for tier in MEMBERSHIP_TIERS}
    for enum_values in _schema_enums(tool, "retrieval_status"):
        assert set(enum_values) == graded
