"""Single source of truth for the roster-evidence contract.

The rules about what evidence may add a candidate to a roster, and what evidence
proves a roster is *complete*, were previously written down twice: as prose in
``prompts.ROSTER_SYNC_USER`` for the model to read, and as predicates in
``handlers`` to enforce. Nothing kept the two in sync, so they drifted — the
prompt would tell a model that a Ballotpedia race page was acceptable
completeness evidence while the handler rejected it, and the model would burn
its entire iteration budget unable to reconcile the instruction with the error.

Both now derive from the definitions here: ``handlers`` imports the data and
validates against it, and ``prompts`` embeds :func:`render_membership_rules` and
:func:`render_completeness_rules` rather than restating them. Changing a rule in
one place is no longer possible.

This module is deliberately free of judgment calls. It encodes *structural*
facts about a source object — its class, whether its content was retrieved or
merely snippeted, how many independent domains back it. Whether the retrieved
text actually says what it is claimed to say is reading comprehension and is
adjudicated elsewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable
from urllib.parse import urlparse

from .roster import ROSTER_CAP

# ---------------------------------------------------------------------------
# Source classes
# ---------------------------------------------------------------------------

#: Every class a roster source may be filed under. ``other`` is a parking slot
#: for input that could not be classified and never satisfies the contract.
SOURCE_CLASSES: FrozenSet[str] = frozenset({"official", "ballotpedia", "fec", "news", "campaign", "other"})

#: Classes that can actually carry roster evidence.
QUALIFYING_SOURCE_CLASSES: FrozenSet[str] = SOURCE_CLASSES - {"other"}

#: Classes whose authority waives the tier-3 two-domain corroboration rule.
AUTHORITATIVE_SOURCE_CLASSES: FrozenSet[str] = frozenset({"official", "fec"})

#: Free-form labels models emit for roster evidence, mapped onto the classes
#: above. Mirrors ``source_types.SOURCE_TYPE_ALIASES``, which exists for the same
#: reason: models reliably invent plausible synonyms for enum values.
SOURCE_CLASS_ALIASES: Dict[str, str] = {
    "article": "news",
    "ballot": "official",
    "certified ballot": "official",
    "election authority": "official",
    "election official": "official",
    "election results": "official",
    "filing": "official",
    "government": "official",
    "gov": "official",
    "media": "news",
    "news article": "news",
    "newspaper": "news",
    "party": "official",
    "party list": "official",
    "press": "news",
    "qualified candidates": "official",
    "secretary of state": "official",
    "sos": "official",
    "state": "official",
    "state election authority": "official",
    "campaign site": "campaign",
    "campaign website": "campaign",
    "candidate site": "campaign",
    "candidate website": "campaign",
    "official campaign": "campaign",
    "fec filing": "fec",
    "federal election commission": "fec",
    "encyclopedia": "ballotpedia",
    "wiki": "ballotpedia",
    "wikipedia": "ballotpedia",
}

#: Election-stage values ``set_race_identity`` and ``update_race_field`` accept.
CONTEST_STAGES: FrozenSet[str] = frozenset(
    {
        "pre_primary",
        "post_primary_general",
        "runoff",
        "top_two",
        "top_four_rcv",
        "uncontested",
        "special",
        "unknown",
    }
)


# ---------------------------------------------------------------------------
# Evidence tiers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceTier:
    """One grade of roster evidence.

    ``retrieval_status`` distinguishes a page whose content the agent actually
    fetched from a search-result snippet it merely saw. That distinction is
    provenance, not a model claim — the agent loop injects its real fetch trace
    into editing calls, so a fabricated citation cannot self-report as retrieved.
    """

    tier: int
    retrieval_status: str
    source_classes: FrozenSet[str]
    summary: str
    rejection_reason: str


MEMBERSHIP_TIERS: tuple[EvidenceTier, ...] = (
    EvidenceTier(
        tier=1,
        retrieval_status="content",
        source_classes=AUTHORITATIVE_SOURCE_CLASSES,
        summary="retrieved official election-authority or FEC page content",
        rejection_reason="tier 1 requires retrieved page content from an official or FEC source",
    ),
    EvidenceTier(
        tier=2,
        retrieval_status="content",
        source_classes=frozenset({"campaign", "ballotpedia", "news"}),
        summary="retrieved dated campaign, exact-election Ballotpedia, or credible news page content",
        rejection_reason="tier 2 requires retrieved page content from a campaign, Ballotpedia, or news source",
    ),
    EvidenceTier(
        tier=3,
        retrieval_status="snippet",
        source_classes=QUALIFYING_SOURCE_CLASSES,
        summary=(
            "a search-result snippet for a page that could not be retrieved; requires two independent "
            "domains unless the source is official or FEC"
        ),
        rejection_reason="tier 3 requires a search-result snippet from a qualifying source",
    ),
)

#: Tiers that prove a roster listing is *complete*. A snippet cannot: partial
#: text from a list page is indistinguishable from a truncated one.
COMPLETENESS_TIERS: FrozenSet[int] = frozenset({1, 2})

#: Classes that may carry completeness evidence. Ballotpedia belongs here
#: because its per-race election pages publish the full qualified field, and
#: RaceJSON treats ``ballotpedia_url`` as the canonical roster pointer.
COMPLETENESS_SOURCE_CLASSES: FrozenSet[str] = frozenset({"official", "news", "ballotpedia"})

#: Classes that can enumerate a field of candidates, and so can support an
#: argument from a candidate's *absence* from a listing. A campaign site is
#: excluded: it speaks for one candidate and never enumerates opponents.
ROSTER_LISTING_SOURCE_CLASSES: FrozenSet[str] = QUALIFYING_SOURCE_CLASSES - {"campaign"}

#: Minimum distinct domains behind a candidate addition backed only by tier-3
#: snippets from non-authoritative sources.
TIER3_CORROBORATING_DOMAINS = 2

#: How many years around the race year count as current-cycle publication.
CYCLE_LOOKBACK_YEARS = 2


def tier_for(tier: Any) -> EvidenceTier | None:
    """Return the tier definition for a numeric grade, or None if unrecognized."""
    for candidate in MEMBERSHIP_TIERS:
        if candidate.tier == tier:
            return candidate
    return None


def tier_rejection_reason(source: Dict[str, Any]) -> str | None:
    """Return why a source's tier/retrieval grade is invalid, or None if valid.

    Structural only: this checks that the claimed grade is internally consistent
    with the source's class and retrieval status. It says nothing about whether
    the evidence text supports the claim being made.
    """
    tier = source.get("evidence_tier")
    status = source.get("retrieval_status")
    definition = tier_for(tier)
    if definition is None:
        return f"evidence_tier {tier!r}/retrieval_status {status!r} is not a recognized evidence grade"
    if status != definition.retrieval_status or source.get("type") not in definition.source_classes:
        return definition.rejection_reason
    return None


def lacks_tier3_corroboration(sources: Iterable[Dict[str, Any]]) -> bool:
    """True when an addition rests only on uncorroborated non-authoritative snippets.

    An addition backed entirely by tier-3 snippets needs either an authoritative
    source or two independent domains. Attaching evidence to a candidate already
    on the roster is a different operation and does not need this.
    """
    qualifying = list(sources)
    if not qualifying or not all(source.get("evidence_tier") == 3 for source in qualifying):
        return False
    if any(source.get("type") in AUTHORITATIVE_SOURCE_CLASSES for source in qualifying):
        return False
    domains = {urlparse(str(source.get("url"))).netloc.lower() for source in qualifying}
    return len(domains) < TIER3_CORROBORATING_DOMAINS


def classify_source_class(raw_type: Any, *, title: str | None, url: str | None, host: str) -> str:
    """Map a free-form roster source label onto a known source class.

    Host evidence is checked first, then the model's label via the recognized set
    and :data:`SOURCE_CLASS_ALIASES`. Classification never depends on the label
    being well-formed: a plausible synonym such as ``"web"`` or
    ``"election_authority"`` used to be parked in ``"other"``, which can never
    satisfy the contract, so valid Ballotpedia and official sources were rejected
    on a spelling technicality.
    """
    title_and_url = f"{title or ''} {url or ''}".casefold()

    # Host evidence outranks the model's label. The authoritative classes waive
    # the tier-3 corroboration rule, so they must be earned by the host (or a
    # party qualified-candidate list title) rather than self-declared —
    # otherwise any page could be relabelled to bypass that guard.
    host_class: str | None = None
    if host == "ballotpedia.org" or host.endswith(".ballotpedia.org"):
        host_class = "ballotpedia"
    elif host == "fec.gov" or host.endswith(".fec.gov"):
        host_class = "fec"
    elif host.endswith(".gov") or re.search(r"\bqualified\b.*\bcandidates?\b", title_and_url):
        host_class = "official"
    if host_class:
        return host_class

    label = str(raw_type or "").strip().lower().replace("_", " ").replace("-", " ")
    label = re.sub(r"\s+", " ", label)
    claimed = label if label in SOURCE_CLASSES and label != "other" else SOURCE_CLASS_ALIASES.get(label)
    if claimed in AUTHORITATIVE_SOURCE_CLASSES:
        # Unverifiable authority claim: keep the source usable but strip the waiver.
        return "news"
    if claimed:
        return claimed
    return "other"


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


def _class_list(classes: Iterable[str]) -> str:
    return ", ".join(sorted(classes))


def render_membership_rules() -> str:
    """Render the evidence contract for adding a candidate to the roster."""
    tiers = "\n".join(f"  Tier {tier.tier}: {tier.summary}." for tier in MEMBERSHIP_TIERS)
    return f"""\
CRITICAL — add_candidate evidence contract (enforced by the tool, not advisory):
- Evidence is graded. The tool accepts these grades and no others:
{tiers}
- Qualifying source classes: {_class_list(QUALIFYING_SOURCE_CLASSES)}. Anything
  that cannot be classified is filed as "other" and never qualifies on its own.
- Every qualifying source needs all of: a stable http(s) URL, a title, evidence
  text naming the candidate and this exact contest, this race's race_id, and a
  publication/filing date within {CYCLE_LOOKBACK_YEARS} years of the race year.
- A tier-3 snippet must carry enough candidate-and-contest context by itself. A
  bare title or ambiguous fragment does not qualify.
- Generic bios, historical tables, undated pages, and wrong-cycle material never
  qualify at any tier.
- Confirm the candidate's PARTY from that same source — never guess the party.
- Never invent, auto-complete, or infer a name from an ambiguous snippet, a
  partial match, or a similarly-named unrelated person. If the official roster
  failed to load, run more targeted searches rather than reconstructing a roster
  from generic results.
- If you cannot confirm a candidate exists in this race, do not add them. A
  missing minor-party candidate is far better than a fabricated one."""


def render_completeness_rules() -> str:
    """Render the evidence contract for proving a roster is complete."""
    tier_labels = ", ".join(f"tier {tier}" for tier in sorted(COMPLETENESS_TIERS))
    return f"""\
Candidate-specific sources prove that the people listed belong; they do not
prove nobody was omitted. finalize_roster therefore requires separate
completeness_sources, graded {tier_labels} — meaning content you actually
FETCHED this run. A search snippet is rejected, because partial text from a list
page cannot be distinguished from a truncated one.
- Accepted classes: {_class_list(COMPLETENESS_SOURCE_CLASSES)}.
- The sources must TOGETHER name every candidate on your proposed roster, or
  identify themselves as qualified, certified, official-ballot, or otherwise
  complete candidate lists. No single source has to name everyone.
- Many states publish one qualified-candidate list PER PARTY. Supply each
  party's list and they compose into the whole field. An entry reading "No
  Nominations", "none", or an explicitly empty district on such a list is
  positive evidence that the party fielded nobody — use it. That is how an
  uncontested race is proven: one party's list names the sole candidate and the
  other party's list shows no nomination for the same district.
- Quote the page's own field-listing sentence VERBATIM in `evidence`. Do not
  paraphrase it. A paraphrase that hedges — "candidates include A and B",
  "among the candidates are A and B" — asserts a partial list and is rejected,
  even when the page you fetched did state the full field. Copy the sentence as
  written, e.g. "A and B are running in the general election for <contest>".
- It must name this exact contest and district. A state election-authority
  landing page that never names this district does not qualify.
- For a special election, it must explicitly identify the special contest and
  its verified date.
- When nothing else lists the full field, fetch the Ballotpedia race page."""


#: What counts as a candidate genuinely leaving the race. Stated once because it
#: is asserted in three places — the prompt that instructs the model, the error
#: the tool returns when it refuses, and the question the adjudicator is asked.
#: Three hand-written copies is how the prompt and the handler drifted apart in
#: the first place.
REMOVAL_GROUNDS: tuple[str, ...] = (
    "withdrew or dropped out",
    "was disqualified",
    "lost a completed primary, runoff, or convention",
    "is a former officeholder who is not a candidate this cycle",
)


def removal_grounds_sentence() -> str:
    """The grounds as one clause, for embedding in an error or a prompt line."""
    return ", ".join(REMOVAL_GROUNDS[:-1]) + f", or {REMOVAL_GROUNDS[-1]}"


def render_removal_rules() -> str:
    """Render the rules for taking a candidate off the roster."""
    grounds = "\n".join(f"  - {ground}" for ground in REMOVAL_GROUNDS)
    return f"""\
IMPORTANT — remove_candidate rules:
- Call remove_candidate only when the candidate has actually left this race:
{grounds}
  State which one plainly in the reason. The tool judges the reason you give, so
  write what happened rather than a formula — it is read, not pattern-matched.
- Do NOT use remove_candidate to fix data quality issues, biography errors, or
  anything else about the candidate's profile. Those are handled in later phases.
- Absence from a page is not an exit. If you found no evidence this person was
  ever a candidate here, call remove_candidate with not_on_roster=true and cite
  the roster listing for this exact race that enumerates the field without them.
  Do not force that into a withdrawal reason.
- Do NOT infer a result from an empty or stale page, a missing listing, or a
  generated URL that failed to load, and never infer the result of an election
  scheduled after the current date.
- If you are unsure whether someone was eliminated, search their name plus the
  primary result before deciding, and keep them if uncertainty remains. A stale
  candidate is a smaller error than a deleted real one."""


def render_roster_cap_rules() -> str:
    """Render the roster size cap, sourced from the same constant that enforces it."""
    per_major_party = ROSTER_CAP // 2
    return f"""\
Keep the roster to ACTIVE, MAJOR candidates. The authoritative source may list
dozens of declared, minor, perennial, or historical candidates — do NOT add them
all. Cap the roster at {ROSTER_CAP} candidates, balanced across the major parties
where possible (up to {per_major_party} Democratic and {per_major_party}
Republican), plus a clearly notable third-party nominee.
- NEVER add a candidate who is not actively running in THIS race for THIS cycle:
  exclude term-limited or not-seeking-re-election incumbents, FORMER
  officeholders who already left office and have not filed again this cycle,
  candidates whose candidacy was for a prior cycle or a past recall,
  withdrawn/eliminated candidates, and long-shot/perennial filers when the field
  is already large.
- Prefer nominees and the most prominent declared candidates (sitting
  officeholders, well-funded or widely-covered contenders) over minor filers.
- If the roster already contains the major candidates, do NOT pad it with minor
  names just because a source lists them. A tight, accurate roster of the real
  contenders is the goal — not an exhaustive ballot dump."""
