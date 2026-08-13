"""Reading-comprehension judgments about roster evidence, made by a model.

Whether a retrieved page actually *says* what a citation claims — that it names
this exact contest, that it enumerates a field without a given candidate, that a
stated removal reason describes a real withdrawal — is reading comprehension.
The regexes that used to answer these questions graded English prose, and the
commit history of ``handlers`` is a record of them oscillating: each fix either
rejected correctly-reasoned edits whose wording differed, or opened a hole.

This module answers those questions with a cheap model instead. Three properties
make that sound rather than circular:

1. **Structural gates run first.** ``roster_contract`` decides class, tier, URL
   validity, and corroboration before anything reaches a model. The adjudicator
   never sees a source that already failed a cheap deterministic check.
2. **It is a different model on a bounded question.** The research model produced
   the evidence and has momentum toward its own conclusion. The adjudicator is
   shown only the evidence text and the claim, with no context about what the
   caller wants the answer to be.
3. **Its verdict is recorded.** The reason is persisted onto the source and
   returned verbatim to the calling agent, so a rejection is inspectable after
   the fact instead of being a flaky gate nobody can debug.

Determinism: pinned model, temperature 0, and an in-process cache keyed by
``(claim, url, evidence)``. Provider-side drift is still possible, which is why
:data:`ADJUDICATOR_MODEL` is pinned to an explicit version rather than a floating
alias — a silent upgrade would move a publish gate with no commit to point at.

The tier choice is deliberate and is explained at
:data:`shared.model_catalog.ADJUDICATOR_MODEL`. Two requirements rule out the
bargain tiers regardless of price: the model must accept ``temperature=0``, or
the gate cannot be pinned; and it must still answer under a 400-token ceiling,
because a model that spends its whole budget on reasoning and returns empty
content reads, on a fail-closed gate, as a rejection of valid evidence.

Availability: this gate **fails closed**. If the provider is unreachable, out of
quota, or returns something unparseable, the claim is rejected with a reason
saying so. An unavailable judge must not become an open door to the roster.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping

from shared.model_catalog import ADJUDICATOR_MODEL as _ADJUDICATOR_MODEL
from shared.model_catalog import ROSTER_COMPLETENESS_REVIEW_MODEL

logger = logging.getLogger("pipeline")

#: The model is pinned in :mod:`shared.model_catalog` — see the notes on
#: ``ADJUDICATOR_MODEL`` there for why it is that model and not a profile role.
#: The short version: this gate sits in front of publication, so a floating
#: choice would let a provider-side upgrade move it with no commit to point at,
#: and it must differ from every profile's research and roster models or the
#: independence claim in this module's docstring is not true.
#: ``scripts/check_model_catalog.py`` enforces both properties.
ADJUDICATOR_MODEL = _ADJUDICATOR_MODEL

ADJUDICATOR_TEMPERATURE = 0.0
ADJUDICATOR_MAX_TOKENS = 400
ADJUDICATOR_TIMEOUT_SECONDS = 30.0


class Claim:
    """The bounded questions the adjudicator is allowed to be asked."""

    #: This source establishes the candidate is running in this exact contest.
    MEMBERSHIP = "membership"
    #: This source enumerates the field for this contest and omits the candidate.
    OMISSION = "omission"
    #: This source shows the candidate belongs to a different contest.
    WRONG_CONTEST = "wrong_contest"
    #: This source is a complete listing of the field for this contest.
    COMPLETENESS = "completeness"
    #: This free-text reason describes an actual exit from the race.
    WITHDRAWAL = "withdrawal"


_CLAIM_QUESTIONS: Dict[str, str] = {
    Claim.MEMBERSHIP: (
        "Does this source establish that {subject} is a candidate in {contest}? "
        "It must name the person and identify that exact office, district, and election cycle. "
        "A source about a different office, a different district with the same number, or a "
        "prior cycle does NOT establish it. "
        "Tabular sources carry their office in a section heading or column rather than in each "
        "row: a row reading 'District 2 | Jane Roe' under a heading such as 'CONGRESSIONAL "
        "DISTRICTS' does identify a U.S. House contest, and a filing date or document title "
        "supplies the cycle. Read the whole evidence string together — do not require every "
        "element to appear in one sentence."
    ),
    Claim.OMISSION: (
        "Does this source enumerate the field of candidates for {contest} while NOT including "
        "{subject}? Answer true only if the text actually lists multiple candidates for this "
        "contest, so that the absence is meaningful. A page that is blocked, empty, truncated, "
        "or that lists candidates for some other contest does NOT establish an omission."
    ),
    Claim.WRONG_CONTEST: (
        "Does this source show that {subject} is running for an office OTHER than {contest}? "
        "It must name the person and identify the different office or district they are actually "
        "seeking in the current cycle."
    ),
    Claim.COMPLETENESS: (
        "Is this source presenting the FIELD of candidates for {contest} — a listing meant to be "
        "the whole set, rather than a passing mention of one or two people? "
        "Answer true if it presents itself as a qualified, certified, or official ballot list, OR "
        "if it enumerates the candidates for this exact contest in the form of a field listing "
        "(for example 'the candidates in the general election for X are A and B'). "
        "Do not require all names to appear in this same source when it explicitly identifies the exact-contest "
        "general election and states the total field size (for example 'General Election — 6 "
        "candidates'); candidate membership is enforced separately from retrieved sources. "
        "Do not require the words 'certified', 'complete', or 'official' — a state's own certified list and a "
        "reference page's standard full-field sentence both qualify, and a two-candidate general "
        "election legitimately has only two candidates. "
        "An official list covering only ONE party also qualifies, because such lists are combined "
        "with the other parties' lists to establish the whole field: answer true for a state "
        "party-primary candidate list that covers this contest's district, INCLUDING when its "
        "entry for that district reads 'No Nominations', 'none', or is otherwise explicitly empty "
        "— an authoritative statement that a party fielded nobody is real evidence about the "
        "field, not an absence of evidence. "
        "The roster being ratified is: {subject}. The product intentionally keeps a bounded roster "
        "of active nominees and notable candidates, so a genuine field listing may contain additional "
        "minor or write-in candidates without contradicting this selected roster. Judge whether the "
        "source supports the people it does cover by IDENTITY, not string equality. "
        "The same person is routinely written differently across sources: 'Andrew Harris' and "
        "'Andy Harris', 'James P. McGovern' and 'Jim McGovern', 'Incumbent Harris', initials, "
        "maiden or married names, or a surname alone once introduced. Treat those as the same "
        "person. A sentence merely naming the Democratic and Republican nominees, or saying they are "
        "the nominees for their respective parties, is NOT a whole-field listing and cannot establish "
        "that no third-party nominee exists. By contrast, a reference page's election section that "
        "explicitly says 'A and B are running in the general election' and presents them as its candidate "
        "field is a full-field listing, even when there are only two candidates. Answer false if the source contradicts the roster or covers "
        "a different contest — not merely because it contains additional low-profile candidates or a "
        "name is spelled or shortened differently. "
        "Answer false if it is a page about a single candidate, an evidently partial or truncated "
        "list, a blocked or empty page, a list for a different contest, or a landing page that "
        "never names this specific contest."
    ),
    Claim.WITHDRAWAL: (
        "Does this stated reason describe {subject} actually LEAVING or never entering {contest} "
        "— withdrawing, dropping out, being disqualified, losing a completed primary or "
        "convention, or being a former officeholder who is not a candidate this cycle? Answer "
        "false if it merely describes a data-quality problem, a biography error, or absence from "
        "some page."
    ),
}

_SYSTEM = """\
You are a strict evidence adjudicator for an election data pipeline. You are \
shown one piece of evidence and one yes/no question about what it establishes.

Judge ONLY what the evidence text actually says. Do not use outside knowledge \
about the race, the candidate, or who is likely running. If the text is empty, \
truncated, blocked, off-topic, or does not address the question, the answer is \
false.

Do not be generous. A wrong "true" puts fabricated data in front of voters. But \
do not demand specific phrasing either: real election authorities word things \
inconsistently, and an official certified list that happens not to use the word \
"certified" is still a certified list. Judge substance, not wording.

Reply with JSON only: {"supports": true|false, "reason": "<one sentence>"}
The reason is shown verbatim to the agent that supplied the evidence, so make it \
say precisely what was missing or wrong."""


@dataclass(frozen=True)
class Verdict:
    """One adjudication result. ``supports`` is the gate; ``reason`` is the audit trail."""

    supports: bool
    reason: str
    model: str = ADJUDICATOR_MODEL
    #: True when this verdict came from a failure path rather than a real judgment.
    unavailable: bool = False

    def to_record(self) -> Dict[str, Any]:
        """Shape persisted onto the source object so a decision survives the run."""
        record = {"supports": self.supports, "reason": self.reason, "model": self.model}
        if self.unavailable:
            record["unavailable"] = True
        return record


def _unavailable(detail: str) -> Verdict:
    """Fail closed. An unreachable judge must not become an open door."""
    return Verdict(
        supports=False,
        reason=f"evidence could not be adjudicated ({detail}); the roster gate fails closed",
        unavailable=True,
    )


def format_contest_label(race_json: Mapping[str, Any] | None, race_id: str) -> str:
    """Describe the contest in words rather than handing over the bare race_id.

    A slug is ambiguous to a judge that has nothing else to go on:
    ``az-house-07-2026`` reads as naturally as Arizona's *state* House district
    7 as it does the U.S. House seat it actually is. The adjudicator then
    rejects perfectly good congressional evidence for describing the "wrong"
    contest, discovery never finalizes, and every ``<state>-house-<n>`` race
    stalls. The profile already knows its own office and jurisdiction, so say
    them and keep the id only as a trailing hint.
    """
    if not isinstance(race_json, Mapping):
        return race_id
    parts = [str(race_json.get(key) or "").strip() for key in ("office", "jurisdiction")]
    parts = [part for part in parts if part]
    if not parts:
        return race_id
    label = " — ".join(parts)
    year = str(race_json.get("election_date") or "")[:4]
    if year.isdigit():
        label = f"{label}, {year} election"
    return f"{label} (race_id {race_id})"


def _cache_key(claim: str, subject: str, contest: str, evidence: str) -> tuple:
    return (claim, subject.casefold(), contest.casefold(), evidence.strip().casefold())


#: Process-local memo so a retried tool call does not re-pay for the same judgment.
_VERDICT_CACHE: Dict[tuple, Verdict] = {}


def clear_cache() -> None:
    """Drop memoized verdicts. Used by tests; harmless in production."""
    _VERDICT_CACHE.clear()


def _build_user_prompt(*, claim: str, subject: str, contest: str, source: Mapping[str, Any]) -> str:
    question = _CLAIM_QUESTIONS[claim].format(subject=subject or "this candidate", contest=contest)
    parts = [f"QUESTION: {question}", ""]
    title = str(source.get("title") or "").strip()
    url = str(source.get("url") or "").strip()
    published = str(source.get("published_at") or "").strip()
    evidence = str(source.get("evidence") or source.get("text") or "").strip()
    if title:
        parts.append(f"SOURCE TITLE: {title}")
    if url:
        parts.append(f"SOURCE URL: {url}")
    if published:
        parts.append(f"PUBLISHED: {published}")
    parts.append("")
    parts.append("EVIDENCE TEXT:")
    parts.append(evidence or "(no evidence text was supplied)")
    return "\n".join(parts)


def _parse_verdict(content: str) -> Verdict | None:
    """Parse the model's JSON reply, tolerating code fences and surrounding prose."""
    text = (content or "").strip()
    if not text:
        return None
    if "```" in text:
        chunks = [chunk for chunk in text.split("```") if "{" in chunk]
        text = chunks[0] if chunks else text
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or "supports" not in payload:
        return None
    reason = str(payload.get("reason") or "").strip() or "no reason given"
    return Verdict(supports=bool(payload["supports"]), reason=reason)


async def adjudicate(
    *,
    claim: str,
    subject: str,
    contest: str,
    source: Mapping[str, Any],
    run_budget: Any = None,
    model: str = ADJUDICATOR_MODEL,
) -> Verdict:
    """Judge one bounded question about one piece of evidence.

    Never raises: every failure path returns a fail-closed verdict, because a
    guard that throws inside a tool handler turns a rejected edit into a crashed
    phase.
    """
    if claim not in _CLAIM_QUESTIONS:
        return _unavailable(f"unknown claim {claim!r}")

    evidence = str(source.get("evidence") or source.get("text") or "")
    key = _cache_key(claim, subject, contest, evidence + str(source.get("url") or "") + model)
    cached = _VERDICT_CACHE.get(key)
    if cached is not None:
        return cached

    try:
        from .llm import _call_openrouter

        response = await asyncio.wait_for(
            _call_openrouter(
                [
                    {"role": "system", "content": _SYSTEM},
                    {
                        "role": "user",
                        "content": _build_user_prompt(claim=claim, subject=subject, contest=contest, source=source),
                    },
                ],
                model=model,
                max_tokens=ADJUDICATOR_MAX_TOKENS,
                temperature=ADJUDICATOR_TEMPERATURE,
                run_budget=run_budget,
            ),
            timeout=ADJUDICATOR_TIMEOUT_SECONDS,
        )
        content = response.choices[0].message.content or ""
    except asyncio.TimeoutError:
        logger.warning("Roster adjudicator timed out for claim=%s subject=%s", claim, subject)
        return _unavailable("adjudicator timed out")
    except Exception as exc:  # provider down, quota exhausted, auth failure
        logger.warning("Roster adjudicator unavailable for claim=%s: %s", claim, exc)
        return _unavailable(f"{type(exc).__name__}")

    verdict = _parse_verdict(content)
    if verdict is None:
        logger.warning("Roster adjudicator returned unparseable content for claim=%s", claim)
        return _unavailable("adjudicator returned an unparseable verdict")

    verdict = Verdict(supports=verdict.supports, reason=verdict.reason, model=model)
    _VERDICT_CACHE[key] = verdict
    return verdict


#: Which tool arguments carry evidence, and what claim each is offered in support of.
#: ``subject_key`` names the arg holding the candidate the claim is about; when it is
#: None the claim is about the race as a whole.
_TOOL_EVIDENCE_SPECS: Dict[str, tuple] = {
    # (args_key, claim, subject_key, condition_key)
    "add_candidate": (("roster_sources", Claim.MEMBERSHIP, "name", None),),
    # This tool's argument is "sources", not "roster_sources" — the two roster
    # tools disagree, and reading the wrong key here silently adjudicated nothing.
    "set_candidate_roster_sources": (("sources", Claim.MEMBERSHIP, "candidate_name", None),),
    "remove_candidate": (
        ("sources", Claim.OMISSION, "name", "not_on_roster"),
        ("sources", Claim.WRONG_CONTEST, "name", "wrong_contest"),
    ),
    # The roster being ratified is the subject of a completeness judgment: the
    # question is whether this evidence is consistent with THAT field. Deciding
    # it by string-matching names in the handler blocked MD-01 because its
    # evidence says "Andrew Harris" and the roster says "Andy Harris" — a class
    # of mismatch (nicknames, initials, surname-only) no matcher can enumerate.
    "finalize_roster": (("completeness_sources", Claim.COMPLETENESS, "source_candidate_names", None),),
}


async def collect_roster_adjudications(
    *,
    tool_name: str,
    args: Mapping[str, Any],
    race_id: str,
    contest_label: str | None = None,
    run_budget: Any = None,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Resolve every evidence judgment a roster tool call will need.

    Returns ``{claim: {url: verdict_record}}``. Called from the async agent loop
    so the synchronous editing handlers receive finished verdicts rather than
    having to make a network call themselves.

    Returns empty for tools that carry no evidence, so non-roster tools cost
    nothing. ``remove_candidate`` without ``not_on_roster``/``wrong_contest`` is
    an ordinary withdrawal and is judged on its reason text, not its sources.
    """
    contest = contest_label or race_id
    specs = _TOOL_EVIDENCE_SPECS.get(tool_name)
    results: Dict[str, Dict[str, Dict[str, Any]]] = {}
    if specs:
        for args_key, claim, subject_key, condition_key in specs:
            if condition_key and args.get(condition_key) is not True:
                continue
            sources = args.get(args_key)
            if not isinstance(sources, list) or not sources:
                continue
            subject_value = args.get(subject_key) if subject_key else None
            if isinstance(subject_value, list):
                # finalize_roster's subject is the whole proposed roster.
                subject = ", ".join(str(name).strip() for name in subject_value if str(name).strip())
            else:
                subject = str(subject_value or "")
            verdicts = await adjudicate_sources(
                claim=claim,
                subject=subject,
                contest=contest,
                sources=[source for source in sources if isinstance(source, dict)],
                run_budget=run_budget,
            )
            if verdicts:
                results[claim] = verdicts

    # A withdrawal is argued in prose, not with a source object, so it is judged
    # from the reason text rather than from an evidence list.
    if tool_name == "remove_candidate" and args.get("not_on_roster") is not True and args.get("wrong_contest") is not True:
        reason = str(args.get("reason") or "").strip()
        if reason:
            verdict = await adjudicate(
                claim=Claim.WITHDRAWAL,
                subject=str(args.get("name") or ""),
                contest=contest,
                source={"evidence": reason},
                run_budget=run_budget,
            )
            results[Claim.WITHDRAWAL] = {"": verdict.to_record()}

    return results


async def adjudicate_sources(
    *,
    claim: str,
    subject: str,
    contest: str,
    sources: Iterable[Mapping[str, Any]],
    run_budget: Any = None,
) -> Dict[str, Dict[str, Any]]:
    """Adjudicate several sources concurrently, keyed by URL for handler lookup.

    Returns ``{url: verdict_record}``. Sources without a URL are skipped: the
    handler's structural gate rejects them before a verdict would matter.
    """
    targets = [source for source in sources if str(source.get("url") or "").strip()]
    if not targets:
        return {}
    verdicts = await asyncio.gather(
        *(
            adjudicate(claim=claim, subject=subject, contest=contest, source=source, run_budget=run_budget)
            for source in targets
        )
    )
    result = {str(source["url"]).strip(): verdict.to_record() for source, verdict in zip(targets, verdicts)}
    if claim != Claim.COMPLETENESS or any(verdict.supports for verdict in verdicts):
        return result

    # A field can be established by several sources together even when no one
    # excerpt is sufficient. On that narrow failure, ask a stronger independent
    # reviewer about the combined packet. The synchronous handler still applies
    # source-class, retrieval, exact-contest, and current-cycle gates afterward.
    evidence_parts = []
    for index, source in enumerate(targets, start=1):
        evidence_parts.append(
            f"SOURCE {index}\nTITLE: {source.get('title', '')}\nURL: {source.get('url', '')}\n"
            f"EVIDENCE: {source.get('evidence') or source.get('text') or ''}"
        )
    bundle = await adjudicate(
        claim=Claim.COMPLETENESS,
        subject=subject,
        contest=contest,
        source={
            "title": "Combined exact-contest roster evidence",
            "url": "bundle://roster-completeness",
            "evidence": "\n\n".join(evidence_parts),
        },
        run_budget=run_budget,
        model=ROSTER_COMPLETENESS_REVIEW_MODEL,
    )
    if bundle.supports:
        record = bundle.to_record()
        record["review_scope"] = "combined_sources"
        return {str(source["url"]).strip(): dict(record) for source in targets}
    return result
