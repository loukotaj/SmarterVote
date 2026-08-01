"""Editing tool handler factory for tools-mode agent phases.

``_make_editing_handlers(race_json, log)`` returns a dict of handler
functions keyed by tool name.  Each handler closes over *race_json*,
mutates it in-place, and returns a short confirmation string that the
LLM receives as the tool result.
"""

import json
import re
from datetime import datetime, timezone
from difflib import get_close_matches
from typing import Any, Callable, Dict, Optional
from urllib.parse import unquote, urlparse

# Pattern matching metadata field names (snake_case, no spaces) — clearly not human names
_METADATA_KEY_RE = re.compile(r"^[a-z][a-z0-9_]+$")

from pipeline_client.agent.ballotpedia import default_ballotpedia_race_url
from pipeline_client.agent.evidence import merge_source_lists
from pipeline_client.agent.images import _is_valid_image_url
from pipeline_client.agent.polling_quality import polling_semantic_problem
from pipeline_client.agent.prompts import CANONICAL_ISSUES
from pipeline_client.agent.source_types import normalize_source_type

_CANONICAL_ISSUE_SET = set(CANONICAL_ISSUES)
_ROSTER_SOURCE_TYPES = {"official", "ballotpedia", "fec", "news", "campaign", "other"}
# Source classes that can actually carry roster evidence. "other" is a parking
# slot for unclassifiable input and never qualifies on its own.
_QUALIFYING_ROSTER_SOURCE_TYPES = {"official", "fec", "campaign", "ballotpedia", "news"}
# Free-form labels models emit for roster evidence, mapped onto the classes
# above. Mirrors source_types.SOURCE_TYPE_ALIASES, which exists for the same
# reason: models reliably invent plausible synonyms for enum values.
_ROSTER_SOURCE_TYPE_ALIASES = {
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
_CONTEST_STAGES = {
    "pre_primary",
    "post_primary_general",
    "runoff",
    "top_two",
    "top_four_rcv",
    "uncontested",
    "special",
    "unknown",
}


def _roster_source_text(source: Dict[str, Any]) -> str:
    return unquote(" ".join(str(source.get(key) or "") for key in ("title", "evidence", "url"))).casefold()


def _source_supports_exact_contest(source: Dict[str, Any], *, race_id: str) -> bool:
    """Reject same-number state-legislative evidence for federal House races."""
    match = re.fullmatch(r"[a-z]{2}-house-(\d{1,2})-(?:19|20)\d{2}", race_id)
    if not match:
        return True
    district = str(int(match.group(1)))
    text = _roster_source_text(source)
    federal_house = bool(
        re.search(r"\b(?:u\.?s\.?|united states)\s+(?:house|representative)", text)
        or re.search(r"\bcongress(?:ional)?\b", text)
    )
    exact_district = bool(
        re.search(rf"\b0*{re.escape(district)}(?:st|nd|rd|th)?\s+(?:congressional\s+)?district\b", text)
        or re.search(rf"\b(?:congressional\s+)?district\s*(?:no\.?\s*)?#?0*{re.escape(district)}\b", text)
        or re.search(rf"\bcd\s*[-#]?\s*0*{re.escape(district)}\b", text)
        # Statewide certification documents commonly title the table
        # "Congressional Districts" and label each row only "District 2".
        or re.search(
            rf"\bcongressional\s+districts\b.{{0,240}}\bdistrict\s*(?:no\.?\s*)?#?0*{re.escape(district)}\b",
            text,
        )
    )
    return federal_house and exact_district


def _source_is_current_cycle(source: Dict[str, Any], *, race_id: str, text: str) -> bool:
    """Check a source belongs to this race's cycle, by publish date or explicit year."""
    year_match = re.search(r"(?:19|20)\d{2}", race_id)
    if not year_match:
        return True
    valid_years = {int(year_match.group()) - 1, int(year_match.group())}
    try:
        published_year = datetime.fromisoformat(str(source.get("published_at") or "").replace("Z", "+00:00")).year
    except ValueError:
        published_year = None
    if published_year is not None:
        return published_year in valid_years
    return any(str(year) in text for year in valid_years)


def _source_names_candidate(text: str, candidate_name: str) -> bool:
    """True when every word of the candidate's name appears in the source text."""
    name_words = re.findall(r"[a-z0-9]+", candidate_name.casefold())
    return bool(name_words) and all(word in text for word in name_words)


def _canonical_roster_name(name: str) -> str:
    """Normalize harmless middle initials and suffixes for roster-set comparison."""
    suffixes = {"jr", "sr", "ii", "iii", "iv"}
    tokens = re.findall(r"[a-z0-9]+", str(name).casefold())
    return " ".join(token for token in tokens if len(token) > 1 and token not in suffixes)


def _source_proves_different_contest(source: Dict[str, Any], *, candidate_name: str, race_id: str) -> bool:
    """Validate that a wrong-contest removal cites real, current, on-topic evidence.

    Deliberately structural. Whether the cited page describes a *different* office
    is a reading-comprehension judgment, and the model that fetched the page has
    already made it. Re-deriving it from keyword patterns does not stop a model
    that wants to fabricate — bogus evidence text matches an office regex just as
    easily as honest text — it only rejects correctly-reasoned removals whose
    wording differs, which is how this check previously failed every race that was
    not a U.S. House contest.
    """
    if source.get("type") not in {"official", "fec", "campaign", "ballotpedia", "news"}:
        return False
    parsed_url = urlparse(str(source.get("url") or ""))
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return False
    text = _roster_source_text(source)
    if not _source_names_candidate(text, candidate_name):
        return False
    return _source_is_current_cycle(source, race_id=race_id, text=text)


def _source_omits_candidate_from_roster(
    source: Dict[str, Any],
    *,
    candidate_name: str,
    race_id: str,
    other_roster_names: list[str],
) -> bool:
    """Return true when a roster listing for THIS race enumerates the field and omits the candidate.

    Absence of evidence is only meaningful from a source that demonstrably *has*
    the roster, so this requires the listing to name at least two other candidates
    currently on the profile. That is what separates a real "never in this race"
    finding from a blocked, empty, or truncated page — the failure mode that
    otherwise deletes real candidates.
    """
    if source.get("type") not in {"official", "fec", "ballotpedia", "news"}:
        return False
    parsed_url = urlparse(str(source.get("url") or ""))
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return False
    if source.get("race_id") != race_id or not source.get("evidence"):
        return False
    if not _source_supports_exact_contest(source, race_id=race_id):
        return False

    text = _roster_source_text(source)
    if not _source_is_current_cycle(source, race_id=race_id, text=text):
        return False

    # Deliberately no "the candidate must not appear in the evidence text" check.
    # The evidence field holds the model's account of the listing, and the natural
    # way to describe an omission names the person omitted ("enumerates the field
    # without Justin Maldonado", "listed under withdrawn candidates"). Scanning it
    # for the name rejects exactly the well-reasoned removals this path exists to
    # allow. The structural guarantee comes from the corroboration count below:
    # the listing must independently name candidates who are still on the roster.

    corroborating = 0
    for other in other_roster_names:
        other_words = [word for word in re.findall(r"[a-z0-9]+", other.casefold()) if len(word) > 2]
        if other_words and all(word in text for word in other_words):
            corroborating += 1
    return corroborating >= 2


def _normalize_source(source: Any, *, default_type: str = "finance") -> Dict[str, Any] | None:
    """Normalize a lightweight tool-provided source into the shared Source shape."""
    if not isinstance(source, dict) or not source.get("url"):
        return None
    normalized = {
        "url": source["url"],
        "type": normalize_source_type(source.get("type"), url=str(source["url"]), default_type=default_type),
        "last_accessed": source.get("last_accessed") or datetime.now(timezone.utc).isoformat(),
    }
    for key in ("title", "description", "published_at", "checksum", "is_fresh", "is_official_campaign"):
        if source.get(key) is not None:
            normalized[key] = source[key]
    return normalized


def _normalize_observed_sources(sources: Any, research_trace: Any, *, default_type: str = "website") -> list[Dict[str, Any]]:
    """Keep generic sources only when their URL was observed by this agent loop."""
    normalized = [
        source for source in (_normalize_source(item, default_type=default_type) for item in sources or []) if source
    ]
    if not isinstance(research_trace, dict):
        return normalized

    def url_key(raw_url: Any) -> str:
        parsed = urlparse(str(raw_url or "").strip())
        path = parsed.path.rstrip("/") or "/"
        return f"{parsed.scheme.casefold()}://{parsed.netloc.casefold()}{path}?{parsed.query}".rstrip("?")

    observed = {url_key(url) for key in ("researched_urls", "fetched_urls") for url in research_trace.get(key) or []}
    return [source for source in normalized if url_key(source.get("url")) in observed]


def _classify_roster_source_type(raw_type: Any, *, title: str | None, url: str | None, host: str) -> str:
    """Map a free-form roster source label onto a known roster source class.

    Host evidence is checked first, then the model's label via the recognized set
    and ``_ROSTER_SOURCE_TYPE_ALIASES``. Classification never depends on the label
    being well-formed: a plausible synonym such as ``"web"`` or
    ``"election_authority"`` used to be parked in ``"other"``, which can never
    satisfy the roster evidence contract, so valid Ballotpedia and official
    sources were rejected on a spelling technicality.
    """
    title_and_url = f"{title or ''} {url or ''}".casefold()

    # Host evidence outranks the model's label. "official"/"fec" are the classes that
    # waive the tier-3 corroboration rule, so they must be earned by the host (or a
    # party qualified-candidate list title) rather than self-declared — otherwise any
    # page could be relabelled to bypass that guard.
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
    claimed = label if label in _ROSTER_SOURCE_TYPES and label != "other" else _ROSTER_SOURCE_TYPE_ALIASES.get(label)
    if claimed in {"official", "fec"}:
        # Unverifiable authority claim: keep the source usable but strip the waiver.
        return "news"
    if claimed:
        return claimed
    return "other"


def _normalize_roster_source(source: Any, *, race_id: str = "") -> Dict[str, Any] | None:
    """Normalize source evidence used only for candidate roster membership."""
    if not isinstance(source, dict):
        return None
    url = str(source.get("url") or "").strip() or None
    title = str(source.get("title") or "").strip() or None
    evidence = (
        str(
            source.get("evidence")
            or source.get("evidence_text")
            or source.get("text")
            or source.get("context")
            or source.get("snippet")
            or ""
        ).strip()
        or None
    )
    host = urlparse(url or "").netloc.casefold()
    source_type = _classify_roster_source_type(source.get("type"), title=title, url=url, host=host)
    if not any((url, title, evidence)):
        return None
    normalized: Dict[str, Any] = {
        "url": url,
        "type": source_type,
        "title": title,
        "evidence": evidence,
        "last_accessed": source.get("last_accessed") or source.get("retrieved") or datetime.now(timezone.utc).isoformat(),
    }
    for key in ("published_at", "race_id", "evidence_tier", "retrieval_status"):
        if source.get(key) is not None:
            normalized[key] = source[key]
    if source.get("date") is not None and "published_at" not in normalized:
        normalized["published_at"] = source["date"]
    normalized.setdefault("race_id", race_id)
    if evidence and "evidence_tier" not in normalized:
        normalized["evidence_tier"] = 3
        normalized["retrieval_status"] = "snippet"
    return {key: value for key, value in normalized.items() if value is not None}


def _apply_roster_research_provenance(
    source: Dict[str, Any],
    research_trace: Any,
    *,
    require_fetch: bool = False,
    infer_fetched_news: bool = False,
) -> Dict[str, Any] | None:
    """Grade evidence from URLs the current agent loop actually observed.

    Model-provided ``retrieved`` and tier fields are claims, not provenance. The
    loop injects its real search/fetch URL trace into editing calls so fabricated
    citations copied from the goal cannot masquerade as retrieved evidence.
    Direct handler callers that do not provide a trace retain legacy behavior;
    production agent loops always provide one.
    """
    if not isinstance(research_trace, dict):
        return source

    def url_key(raw_url: Any) -> str:
        parsed = urlparse(str(raw_url or "").strip())
        path = parsed.path.rstrip("/") or "/"
        return f"{parsed.scheme.casefold()}://{parsed.netloc.casefold()}{path}?{parsed.query}".rstrip("?")

    url = url_key(source.get("url"))
    researched = {url_key(item) for item in research_trace.get("researched_urls") or []}
    fetched = {url_key(item) for item in research_trace.get("fetched_urls") or []}
    if url in fetched:
        # Models sometimes omit the optional source-type label even after they
        # successfully fetched a conventional news article. Do not discard that
        # real content on a labeling technicality. This promotion is deliberately
        # limited to fetched sources and never grants official/FEC authority.
        if infer_fetched_news and source.get("type") == "other":
            source["type"] = "news"
        source["retrieval_status"] = "content"
        source["evidence_tier"] = 1 if source.get("type") in {"official", "fec"} else 2
        return source
    if require_fetch or url not in researched:
        return None
    source["retrieval_status"] = "snippet"
    source["evidence_tier"] = 3
    return source


def _normalize_observed_roster_sources(
    sources: Any,
    *,
    race_id: str,
    research_trace: Any,
    require_fetch: bool = False,
    infer_fetched_news: bool = False,
) -> list[Dict[str, Any]]:
    normalized = [source for source in (_normalize_roster_source(item, race_id=race_id) for item in sources or []) if source]
    return [
        observed
        for source in normalized
        if (
            observed := _apply_roster_research_provenance(
                source,
                research_trace,
                require_fetch=require_fetch,
                infer_fetched_news=infer_fetched_news,
            )
        )
    ]


def _roster_source_rejection_reason(source: Dict[str, Any], *, candidate_name: str, race_id: str) -> str | None:
    """Return why one persisted source fails the roster-evidence contract, or None if it passes.

    Callers surface the reason verbatim to the model. A generic "not enough
    evidence" message sends it hunting for more sources when the real problem is
    often a single malformed field, which turns one bad call into a retry loop.
    """
    if source.get("type") not in _QUALIFYING_ROSTER_SOURCE_TYPES:
        return (
            f"source type {str(source.get('type'))!r} cannot carry roster evidence; "
            f"use one of: {', '.join(sorted(_QUALIFYING_ROSTER_SOURCE_TYPES))}"
        )
    parsed_url = urlparse(str(source.get("url") or ""))
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return "source needs an absolute http(s) url"
    if source.get("race_id") != race_id:
        return f"source race_id {str(source.get('race_id'))!r} does not match this race ({race_id!r})"
    if not source.get("title"):
        return "source needs a title"
    if not source.get("evidence"):
        return "source needs an 'evidence' (or 'text') quote naming the candidate and contest"
    if not _source_supports_exact_contest(source, race_id=race_id):
        return "evidence does not name this exact federal contest and district"
    name_words = re.findall(r"[a-z0-9]+", candidate_name.lower())
    evidence_text = f"{source.get('title', '')} {source.get('evidence', '')}".lower()
    if not name_words or not all(word in evidence_text for word in name_words):
        return f"evidence text does not contain the full candidate name {candidate_name!r}"
    year_match = re.search(r"(?:19|20)\d{2}", race_id)
    try:
        published = datetime.fromisoformat(str(source.get("published_at") or "").replace("Z", "+00:00"))
    except ValueError:
        published = None
    if year_match:
        valid_years = {int(year_match.group()) - 2, int(year_match.group()) - 1, int(year_match.group())}
        years_label = "/".join(str(year) for year in sorted(valid_years))
        if published is not None:
            if published.year not in valid_years:
                return f"published_at year {published.year} is outside the current cycle ({years_label})"
        elif not any(str(year) in evidence_text for year in valid_years):
            return f"evidence has no current-cycle date; include a {years_label} published_at or cite the year in the text"
    tier = source.get("evidence_tier")
    status = source.get("retrieval_status")
    if tier == 1:
        if status != "content" or source.get("type") not in {"official", "fec"}:
            return "tier 1 requires retrieved page content from an official or FEC source"
        return None
    if tier == 2:
        if status != "content" or source.get("type") not in {"campaign", "ballotpedia", "news"}:
            return "tier 2 requires retrieved page content from a campaign, Ballotpedia, or news source"
        return None
    if tier == 3 and status == "snippet":
        return None
    return f"evidence_tier {tier!r}/retrieval_status {status!r} is not a recognized evidence grade"


def _source_supports_candidate_addition(source: Dict[str, Any], *, candidate_name: str, race_id: str) -> bool:
    """Validate one persisted source against the graded roster-evidence contract."""
    return _roster_source_rejection_reason(source, candidate_name=candidate_name, race_id=race_id) is None


def _qualifying_candidate_addition_sources(
    sources: Any,
    *,
    candidate_name: str,
    race_id: str,
    require_corroboration: bool = True,
) -> list[Dict[str, Any]]:
    """Return qualifying sources, enforcing corroboration for non-authoritative snippets.

    ``require_corroboration`` guards *adding* a candidate to the roster, where an
    uncorroborated snippet is the fabrication risk. Attaching evidence to a
    candidate who is already on the roster is a different operation and does not
    need a second independent domain.
    """
    normalized = [src for src in (_normalize_roster_source(source, race_id=race_id) for source in sources or []) if src]
    qualifying = [
        source
        for source in normalized
        if _source_supports_candidate_addition(source, candidate_name=candidate_name, race_id=race_id)
    ]
    if require_corroboration and qualifying and all(source.get("evidence_tier") == 3 for source in qualifying):
        if any(source.get("type") in {"official", "fec"} for source in qualifying):
            return qualifying
        domains = {urlparse(str(source.get("url"))).netloc.lower() for source in qualifying}
        if len(domains) < 2:
            return []
    return qualifying


def _roster_source_rejection_summary(sources: Any, *, candidate_name: str, race_id: str) -> str:
    """Summarize per-source rejection reasons for a blocked roster edit."""
    normalized = [src for src in (_normalize_roster_source(source, race_id=race_id) for source in sources or []) if src]
    if not normalized:
        return "no usable source objects were supplied"
    reasons = []
    for index, source in enumerate(normalized, start=1):
        reason = _roster_source_rejection_reason(source, candidate_name=candidate_name, race_id=race_id)
        if reason:
            reasons.append(f"source {index} ({source.get('url') or 'no url'}): {reason}")
    if not reasons:
        return (
            "each source is individually valid, but all of them are tier-3 snippets from a single domain; "
            "cite a second independent domain or retrieve official/FEC page content"
        )
    return "; ".join(reasons)


def _roster_completeness_source_rejection_reason(
    source: Dict[str, Any], *, race_id: str, identity: Dict[str, Any]
) -> str | None:
    """Validate evidence that describes the roster as a whole, not one member."""
    if source.get("type") not in {"official", "news"}:
        return "completeness evidence must be an official roster/ballot or retrieved news report"
    parsed_url = urlparse(str(source.get("url") or ""))
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return "source needs an absolute http(s) url"
    if source.get("race_id") != race_id:
        return f"source race_id {str(source.get('race_id'))!r} does not match this race ({race_id!r})"
    if not source.get("title") or not source.get("evidence"):
        return "source needs a title and evidence quoting the complete candidate list"
    if not _source_supports_exact_contest(source, race_id=race_id):
        return "evidence does not name this exact contest and district"
    if source.get("retrieval_status") != "content" or source.get("evidence_tier") not in {1, 2}:
        return "completeness evidence must come from retrieved page content, not a search snippet"

    text = _roster_source_text(source)
    # Real election authorities do not use one fixed phrase. New Jersey publishes
    # "Official List Candidates for US Senate For GENERAL ELECTION", which named
    # the full certified field yet failed a pattern that only accepted "candidate
    # list" in that word order — the authoritative source rejected by the check
    # meant to require an authoritative source.
    if not re.search(
        r"\b(?:qualified|certified|official list|official ballot|candidate list|list of candidates"
        r"|candidates? running|vote for one)\b",
        text,
    ):
        return "evidence does not identify itself as a qualified, certified, ballot, or complete candidate list"

    primary_status = str(identity.get("primary_status") or "")
    if "special" in primary_status.casefold():
        if "special" not in text:
            return "race identity is a special election, but the source does not identify the special contest"
        election_date = str(identity.get("election_date") or "")
        try:
            parsed_date = datetime.fromisoformat(election_date).date()
        except ValueError:
            parsed_date = None
        if parsed_date:
            month = parsed_date.strftime("%B").casefold()
            numeric_dates = {
                parsed_date.isoformat(),
                f"{parsed_date.month}/{parsed_date.day}/{parsed_date.year}",
                f"{parsed_date.month:02d}/{parsed_date.day:02d}/{parsed_date.year}",
            }
            has_date = any(value in text for value in numeric_dates) or bool(
                re.search(rf"\b{month}\s+{parsed_date.day}(?:st|nd|rd|th)?[,]?\s+{parsed_date.year}\b", text)
            )
            if not has_date:
                return f"source does not identify the special-election date {parsed_date.isoformat()}"
    return None


def _get_other_state_candidates(race_id: str, state: str | None) -> set[str]:
    """Retrieve candidate names from other races in the same state/cycle to detect contamination."""
    other_names = set()
    if not state:
        return other_names

    # Determine storage mode from settings
    try:
        from pipeline_client.backend.settings import settings

        storage_mode = settings.storage_mode
        project = settings.firestore_project
    except Exception:
        storage_mode = "local"
        project = None

    if storage_mode == "gcp":
        try:
            from google.cloud import firestore

            db = firestore.Client(project=project) if project else firestore.Client()
            races_ref = db.collection("races").where("state", "==", state).stream()
            for doc in races_ref:
                other_race_id = doc.id
                if other_race_id == race_id:
                    continue
                data = doc.to_dict() or {}
                for cand in data.get("candidates", []):
                    if isinstance(cand, dict) and cand.get("name") and cand.get("withdrawn") is not True:
                        other_names.add(cand["name"].strip())
        except Exception:
            pass
    else:
        try:
            from shared.config import local_paths

            prefix = race_id.split("-")[0].lower() if "-" in race_id else ""
            if not prefix:
                return other_names

            for directory in (local_paths.drafts_dir, local_paths.published_dir):
                if not directory.exists():
                    continue
                for path in directory.glob(f"{prefix}-*.json"):
                    if path.stem == race_id:
                        continue
                    try:
                        with path.open("r", encoding="utf-8") as f:
                            data = json.load(f)
                        if data.get("state") == state:
                            for cand in data.get("candidates", []):
                                if isinstance(cand, dict) and cand.get("name") and cand.get("withdrawn") is not True:
                                    other_names.add(cand["name"].strip())
                    except Exception:
                        continue
        except Exception:
            pass

    return other_names


def _make_editing_handlers(
    race_json: Dict[str, Any], log: Callable, *, restrict_to_candidate: str | None = None
) -> Dict[str, Any]:
    """Build editing-tool handlers closed over *race_json*.

    Returns a ``{tool_name: handler_fn}`` dict compatible with the
    ``extra_tool_handlers`` parameter of ``_agent_loop``.

    When *restrict_to_candidate* is set, every handler that targets a
    specific existing candidate by name is guarded so a call naming a
    *different* candidate is rejected instead of silently applied. This
    matters for per-candidate turns (e.g. the review-iteration pass, which
    runs one ``_agent_loop`` per candidate): without it, a model mistake in
    one candidate's turn (e.g. passing the wrong ``candidate_name``) can
    silently corrupt a *different* candidate's data, since these handlers
    otherwise look up any candidate by name across the whole roster.
    """
    _ALLOWED_CANDIDATE_FIELDS = {"party", "incumbent", "website", "image_url"}
    _ALLOWED_RACE_FIELDS = {
        "description",
        "office",
        "election_date",
        "polling_note",
        "ballotpedia_url",
        "register_to_vote_url",
        "how_to_vote_url",
        "contest_stage",
    }

    def _find_candidate(name: str) -> Optional[Dict[str, Any]]:
        for c in race_json.get("candidates", []):
            if isinstance(c, dict) and c.get("name") == name:
                return c
        return None

    # --- Roster handlers ---

    def add_candidate(args: Dict[str, Any]) -> str:
        name = args["name"]
        _PLACEHOLDER_NAMES = {
            "",
            "unknown",
            "tbd",
            "to be determined",
            "n/a",
            "na",
            "none",
            "dummy",
            "test",
            "placeholder",
            "candidate",
            "sample",
            "example",
            "insert name here",
            "insert candidate name",
            "[candidate name]",
        }
        if name.strip().lower() in _PLACEHOLDER_NAMES or name.strip().startswith("["):
            log("warning", f"    add_candidate('{name}') BLOCKED: placeholder/test name rejected")
            return (
                f"Blocked: '{name}' looks like a placeholder name, not a real candidate. Only add confirmed real candidates."
            )
        if _find_candidate(name):
            return f"Candidate '{name}' already exists — skipping."
        state = race_json.get("state")
        race_id = str(race_json.get("id") or "").strip()
        if state:
            other_state_candidates = _get_other_state_candidates(race_id, state)
            if any(name.strip().lower() == other.lower() for other in other_state_candidates):
                log(
                    "warning",
                    f"    add_candidate('{name}') BLOCKED: candidate is already active in another race in {state}.",
                )
                return (
                    f"Blocked adding '{name}': This candidate is already registered as an active candidate in "
                    f"another race in {state} for this election cycle. A candidate cannot run in multiple concurrent "
                    "statewide or federal contests. Verify the office, district, and candidate name."
                )
        supplied_sources = _normalize_observed_roster_sources(
            args.get("roster_sources"),
            race_id=race_id,
            research_trace=args.get("_research_trace"),
        )
        roster_sources = _qualifying_candidate_addition_sources(supplied_sources, candidate_name=name, race_id=race_id)
        if not roster_sources:
            if isinstance(args.get("_research_trace"), dict) and not supplied_sources:
                detail = "none of the cited URLs appeared in this run's actual search/fetch trace"
            else:
                detail = _roster_source_rejection_summary(supplied_sources, candidate_name=name, race_id=race_id)
            log("warning", f"    add_candidate('{name}') BLOCKED: {detail}")
            return (
                f"Blocked adding '{name}': {detail}. "
                "Provide persisted, dated current-cycle evidence that explicitly names the candidate and exact race. "
                "Retrieved official/FEC content is Tier 1; retrieved campaign, exact-race Ballotpedia, or credible "
                "news content is Tier 2; blocked-page snippets are Tier 3 and require two independent sources unless "
                "the snippet is from an official/FEC source."
            )
        party = str(args.get("party") or "")
        party_key = "democratic" if "democrat" in party.lower() else "republican" if "republican" in party.lower() else ""
        if party_key:
            for existing in race_json.get("candidates", []):
                if not isinstance(existing, dict) or party_key not in str(existing.get("party") or "").lower():
                    continue
                roster_text = " ".join(
                    str(existing.get(field) or "") for field in ("summary", "donor_summary", "voting_summary")
                )
                if re.search(r"\b(?:the )?(?:democratic|republican|gop)?\s*nominee\b", roster_text, re.IGNORECASE):
                    existing_name = existing.get("name") or "existing candidate"
                    log(
                        "warning",
                        f"    add_candidate('{name}') BLOCKED: {existing_name} is already identified "
                        f"as the {party_key.title()} nominee.",
                    )
                    return (
                        f"Blocked adding '{name}': {existing_name} is already the {party_key.title()} nominee. "
                        "Only replace a nominee after a verified withdrawal or disqualification."
                    )
        candidate = {
            "name": name,
            "party": party,
            "incumbent": args.get("incumbent", False),
            "roster_sources": roster_sources,
            "summary": "",
            "summary_sources": [],
            "image_url": None,
            "website": None,
            "social_media": {},
            "career_history": [],
            "education": [],
            "donor_summary": None,
            "donor_source_url": None,
            "voting_summary": None,
            "voting_source_url": None,
            "links": [],
            "issues": {},
        }
        race_json.setdefault("candidates", []).append(candidate)
        log("info", f"    Added candidate: {name} ({args.get('party', '?')})")
        return f"Added candidate '{name}'."

    def remove_candidate(args: Dict[str, Any]) -> str:
        name = args["name"]
        reason = args.get("reason", "").strip()
        candidates = race_json.get("candidates", [])
        if args.get("wrong_contest") is True or args.get("not_on_roster") is True:
            race_id = str(race_json.get("id") or "").strip()
            not_on_roster = args.get("not_on_roster") is True and args.get("wrong_contest") is not True
            normalized_sources = _normalize_observed_roster_sources(
                args.get("sources"), race_id=race_id, research_trace=args.get("_research_trace")
            )

            if not_on_roster:
                target = _find_candidate(name)
                if isinstance(target, dict) and target.get("incumbent") is True:
                    return (
                        f"ERROR: roster-absence removal blocked for '{name}': they are recorded as the incumbent. "
                        "An incumbent missing from one listing is far more likely a bad snippet than a phantom "
                        "candidate. Use a withdrawal/retirement reason with a dated source instead."
                    )
                other_roster_names = [
                    str(candidate.get("name") or "")
                    for candidate in candidates
                    if isinstance(candidate, dict) and candidate.get("name") and candidate.get("name") != name
                ]
                proof = [
                    source
                    for source in normalized_sources
                    if _source_omits_candidate_from_roster(
                        source,
                        candidate_name=name,
                        race_id=race_id,
                        other_roster_names=other_roster_names,
                    )
                ]
                if not proof:
                    return (
                        f"ERROR: roster-absence removal blocked for '{name}'. Cite the best roster listing you have "
                        "for this exact race and cycle — an official/certified candidate list, or the current "
                        "Ballotpedia election page. Its evidence text must name at least two other candidates who "
                        "are on this profile (proving the listing actually loaded and enumerates the field) and "
                        f"must not mention '{name}'. A blocked, empty, or truncated page is not evidence of absence."
                    )
                label = "unlisted"
            else:
                proof = [
                    source
                    for source in normalized_sources
                    if _source_proves_different_contest(source, candidate_name=name, race_id=race_id)
                ]
                if not proof:
                    return (
                        f"ERROR: wrong-contest removal blocked for '{name}'. Provide a current source that names the "
                        "candidate and explicitly identifies the different office/district."
                    )
                label = "wrong-contest"

            active_after = [
                candidate
                for candidate in candidates
                if isinstance(candidate, dict)
                and candidate.get("name") != name
                and candidate.get("name")
                and candidate.get("withdrawn") is not True
            ]
            if not active_after:
                return f"ERROR: {label} removal blocked. Add the verified correct roster before removing '{name}'."
            original_count = len(candidates)
            race_json["candidates"] = [
                candidate for candidate in candidates if not isinstance(candidate, dict) or candidate.get("name") != name
            ]
            if len(race_json["candidates"]) < original_count:
                log("info", f"    Removed {label} candidate: {name} ({reason or proof[0].get('url')})")
                return f"Removed {label} candidate '{name}' from the active roster."
            return f"Candidate '{name}' not found - no action taken."

        # Guard: reject removals that are clearly data-quality fixes rather than
        # actual race withdrawals. Withdrawal reasons must mention a concrete
        # race exit, not merely absence from a page or a generic "lost primary"
        # phrase that models frequently hallucinate during roster repair.
        _EXIT_KEYWORDS = {
            "withdrew",
            "withdrawal",
            "dropped out",
            "drop out",
            "suspended",
            "disqualified",
            "disqualification",
            "ended campaign",
            "exited race",
            "no longer running",
            "not running",
            "retired from race",
        }
        reason_lower = reason.lower()
        has_exit_signal = any(kw in reason_lower for kw in _EXIT_KEYWORDS)
        has_primary_loss_signal = bool(
            re.search(
                r"\b(lost|defeated|eliminated|did not advance)\b.{0,80}\b(primary|runoff|convention)\b",
                reason_lower,
            )
            or re.search(
                r"\b(primary|runoff|convention)\b.{0,80}\b(lost|defeated|eliminated|did not advance)\b",
                reason_lower,
            )
        )
        has_specific_date = bool(
            re.search(
                r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
                r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2},\s+\d{4}\b",
                reason_lower,
            )
            or re.search(r"\b20\d{2}-\d{2}-\d{2}\b", reason_lower)
        )
        has_official_result_signal = bool(
            re.search(
                r"\b(official|certified|results?|election authority|secretary of state|board of elections)\b",
                reason_lower,
            )
        )
        # A retired/departed former officeholder or an explicit prior-cycle
        # candidate who is not running THIS cycle is a legitimate removal even
        # without a withdrawal event — they never entered this race. Require a
        # positive "former"/"prior-cycle" statement AND a "not a current
        # candidate" signal, so this does not reopen the "merely absent from a
        # page" hole the guard exists to close.
        has_former_status_signal = bool(
            re.search(
                r"\bformer\s+(u\.?s\.?\s+)?"
                r"(representative|congress\w*|senator|governor|lieutenant governor|"
                r"officeholder|member of congress|incumbent)\b",
                reason_lower,
            )
            or re.search(r"\bleft office\b", reason_lower)
            or re.search(r"\bretired\b.{0,40}\b(20\d{2}|congress|office|house|senate)\b", reason_lower)
            or re.search(r"\b(prior|previous)[- ]cycle\b", reason_lower)
        )
        has_not_current_signal = any(
            token in reason_lower
            for token in (
                "not a candidate",
                "not a current candidate",
                "not running",
                "not seeking",
                "did not file",
                "has not filed",
                "no longer",
                "not on the ballot",
            )
        )
        has_former_officeholder_signal = has_former_status_signal and has_not_current_signal
        # Evidence outranks phrasing. The keyword scans below grade English prose,
        # which reliably rejects correct removals that happen to be worded
        # differently. When the caller cites a real, current-cycle source that names
        # this candidate, that citation is the stronger signal — accept it and let
        # the reason text be prose rather than an incantation.
        cited_race_id = str(race_json.get("id") or "").strip()
        observed_cited_sources = _normalize_observed_roster_sources(
            args.get("sources"), race_id=cited_race_id, research_trace=args.get("_research_trace")
        )
        has_cited_evidence = any(
            _source_proves_different_contest(source, candidate_name=name, race_id=cited_race_id)
            for source in observed_cited_sources
        )
        has_withdrawal_signal = (
            has_cited_evidence
            or has_exit_signal
            or has_former_officeholder_signal
            # A specific date *or* an explicit official-result citation is enough
            # corroboration for a primary loss; requiring both rejected reasons like
            # "Lost the Democratic primary on June 30, 2026." — a specific dated
            # primary result — just because it didn't also say the word "official".
            or (has_primary_loss_signal and (has_specific_date or has_official_result_signal))
        )

        # Special case: structurally invalid entries (e.g. a metadata key like
        # "updated_utc" accidentally stored as a candidate name) should be
        # physically deleted rather than marked withdrawn.
        is_structural_garbage = bool(_METADATA_KEY_RE.match(name))

        if not has_withdrawal_signal and not is_structural_garbage:
            log(
                "warning",
                f"    ⚠️ remove_candidate('{name}') BLOCKED — reason does not confirm "
                f"a race withdrawal: {reason!r}. Use this tool only when a candidate "
                f"has officially left the race.",
            )
            return (
                f"ERROR: remove_candidate blocked. The reason '{reason}' does not indicate "
                f"that '{name}' has left the race. Only call remove_candidate when a candidate "
                f"has officially withdrawn, dropped out, been disqualified, lost a completed "
                f"contest with an official result source and date, OR is a former officeholder / "
                f"prior-cycle candidate who is not a candidate this cycle — state that explicitly "
                f"(e.g. 'former U.S. Representative who left office in 2023 and is not a candidate "
                f"in 2026'). If instead you found no evidence this person was ever a candidate here, "
                f"call remove_candidate with not_on_roster=true and cite the roster listing for this "
                f"race that enumerates the field without them. Do NOT use this tool to fix data quality issues."
            )

        if is_structural_garbage:
            # Physically delete malformed/non-human entries from the list
            orig_len = len(candidates)
            race_json["candidates"] = [c for c in candidates if not isinstance(c, dict) or c.get("name") != name]
            removed = orig_len - len(race_json["candidates"])
            if removed:
                log("info", f"    🗑️ Deleted malformed candidate entry '{name}' ({removed} removed)")
                return f"Deleted malformed entry '{name}' from candidates list."
            return f"Entry '{name}' not found — no action taken."

        for c in candidates:
            if not isinstance(c, dict):
                continue
            if c.get("name") == name:
                active_after = [
                    other
                    for other in candidates
                    if isinstance(other, dict) and other is not c and other.get("name") and other.get("withdrawn") is not True
                ]
                if not active_after:
                    log(
                        "warning",
                        f"    remove_candidate('{name}') BLOCKED - removing this candidate would leave no active candidates.",
                    )
                    return (
                        f"ERROR: remove_candidate blocked. Removing '{name}' would leave the race with no active candidates. "
                        "Find and add the verified remaining candidate(s) first, or keep this candidate until exit evidence is certain."
                    )
                c["withdrawn"] = True
                c["withdrawal_reason"] = reason or None
                log("info", f"    🚪 Marked withdrawn: {name} ({reason or 'no reason given'})")
                return f"Marked candidate '{name}' as withdrawn ({reason or 'no reason given'}). Data preserved; candidate will be hidden from main race view."
        return f"Candidate '{name}' not found — no action taken."

    def rename_candidate(args: Dict[str, Any]) -> str:
        old_name, new_name = args["old_name"], args["new_name"]
        c = _find_candidate(old_name)
        if not c:
            return f"Candidate '{old_name}' not found."
        c["name"] = new_name
        log("info", f"    Renamed: {old_name} -> {new_name}")
        return f"Renamed '{old_name}' to '{new_name}'."

    def set_candidate_roster_sources(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        race_id = str(race_json.get("id") or "").strip()
        # This candidate is already on the roster, so the corroboration rule that
        # guards *adding* one does not apply — a single valid source is enough to
        # attach evidence to an existing entry.
        supplied_sources = _normalize_observed_roster_sources(
            args.get("sources"), race_id=race_id, research_trace=args.get("_research_trace")
        )
        sources = _qualifying_candidate_addition_sources(
            supplied_sources, candidate_name=name, race_id=race_id, require_corroboration=False
        )
        if not sources:
            if isinstance(args.get("_research_trace"), dict) and not supplied_sources:
                detail = "none of the cited URLs appeared in this run's actual search/fetch trace"
            else:
                detail = _roster_source_rejection_summary(supplied_sources, candidate_name=name, race_id=race_id)
            log("warning", f"    set_candidate_roster_sources('{name}') BLOCKED: {detail}")
            return f"ERROR: no usable roster source for '{name}': {detail}."
        c["roster_sources"] = sources
        log("info", f"    Set {len(sources)} roster source(s) for {name}")
        return f"Set {len(sources)} roster source(s) for '{name}'."

    def set_race_identity(args: Dict[str, Any]) -> str:
        contest_stage = str(args.get("contest_stage") or "unknown").strip().lower()
        if contest_stage not in _CONTEST_STAGES:
            return f"ERROR: contest_stage must be one of: {', '.join(sorted(_CONTEST_STAGES))}."
        identity: Dict[str, Any] = {"contest_stage": contest_stage}
        for key in (
            "office",
            "state",
            "district",
            "election_date",
            "primary_status",
            "official_roster_source_url",
            "known_incumbent",
        ):
            value = args.get(key)
            if value not in (None, ""):
                identity[key] = value
        if isinstance(args.get("known_ineligible_or_not_running"), list):
            identity["known_ineligible_or_not_running"] = [
                str(item) for item in args["known_ineligible_or_not_running"] if str(item).strip()
            ]
        race_json["contest_stage"] = contest_stage
        if identity.get("office") and not race_json.get("office"):
            race_json["office"] = identity["office"]
        if identity.get("state") and not race_json.get("state"):
            race_json["state"] = identity["state"]
        if identity.get("district") and not race_json.get("district"):
            race_json["district"] = identity["district"]
        if identity.get("election_date") and not race_json.get("election_date"):
            race_json["election_date"] = identity["election_date"]
        pipeline_state = race_json.setdefault("pipeline_state", {})
        pipeline_state["race_identity"] = identity
        log("info", f"    Locked race identity ({contest_stage})")
        return "Recorded race identity brief."

    def finalize_roster(args: Dict[str, Any]) -> str:
        race_id = str(race_json.get("id") or "").strip()
        identity = (race_json.get("pipeline_state") or {}).get("race_identity")
        if not isinstance(identity, dict) or not identity.get("office") or not identity.get("contest_stage"):
            return "ERROR: roster finalization blocked. Lock the exact office and contest stage with set_race_identity."

        completeness_sources = _normalize_observed_roster_sources(
            args.get("completeness_sources"),
            race_id=race_id,
            research_trace=args.get("_research_trace"),
            require_fetch=True,
            infer_fetched_news=True,
        )
        completeness_rejections = [
            reason
            for source in completeness_sources
            if (reason := _roster_completeness_source_rejection_reason(source, race_id=race_id, identity=identity))
        ]
        qualifying_completeness = [
            source
            for source in completeness_sources
            if _roster_completeness_source_rejection_reason(source, race_id=race_id, identity=identity) is None
        ]
        if not qualifying_completeness:
            detail = "; ".join(completeness_rejections) if completeness_rejections else "no sources were supplied"
            return (
                "ERROR: roster finalization blocked. Candidate-level evidence proves membership, not completeness. "
                "Provide retrieved completeness_sources quoting the authoritative qualified/certified/ballot list "
                f"for this exact contest ({detail})."
            )

        proposed_specs = args.get("candidates")
        if proposed_specs is not None:
            if not isinstance(proposed_specs, list) or not proposed_specs:
                return "ERROR: roster finalization blocked. The proposed candidates list must not be empty."
            if len(proposed_specs) > 8:
                return "ERROR: roster finalization blocked. The active roster exceeds the eight-candidate cap."
            proposed_names = [str(spec.get("name") or "").strip() for spec in proposed_specs if isinstance(spec, dict)]
            if len(proposed_names) != len(proposed_specs) or any(not name for name in proposed_names):
                return "ERROR: roster finalization blocked. Every proposed candidate needs a non-empty name."
            normalized_names = [_canonical_roster_name(name) for name in proposed_names]
            if len(set(normalized_names)) != len(normalized_names):
                return "ERROR: roster finalization blocked. The proposed roster contains duplicate candidate names."
            extracted_names = [str(name).strip() for name in args.get("source_candidate_names") or [] if str(name).strip()]
            if {_canonical_roster_name(name) for name in extracted_names} != set(normalized_names):
                return (
                    "ERROR: roster finalization blocked. source_candidate_names must match the proposed candidate "
                    "roster extracted from the completeness evidence (middle initials and suffixes may differ)."
                )

            existing_by_name = {
                str(candidate.get("name") or "").strip().casefold(): candidate
                for candidate in race_json.get("candidates", [])
                if isinstance(candidate, dict) and candidate.get("name")
            }
            active_candidates = []
            missing_evidence = []
            for spec in proposed_specs:
                name = str(spec.get("name") or "").strip()
                supplied_sources = _normalize_observed_roster_sources(
                    spec.get("roster_sources"),
                    race_id=race_id,
                    research_trace=args.get("_research_trace"),
                )
                candidate_sources = _qualifying_candidate_addition_sources(
                    supplied_sources + qualifying_completeness,
                    candidate_name=name,
                    race_id=race_id,
                    require_corroboration=False,
                )
                if not candidate_sources:
                    missing_evidence.append(name)
                    continue
                candidate = dict(existing_by_name.get(name.casefold()) or {})
                candidate.update(
                    {
                        "name": name,
                        "party": str(spec.get("party") or "Unknown"),
                        "incumbent": bool(spec.get("incumbent", candidate.get("incumbent", False))),
                        "roster_sources": candidate_sources,
                        "withdrawn": False,
                        "withdrawal_reason": None,
                    }
                )
                candidate.setdefault("summary", "")
                candidate.setdefault("summary_sources", [])
                candidate.setdefault("image_url", None)
                candidate.setdefault("website", None)
                candidate.setdefault("social_media", {})
                candidate.setdefault("career_history", [])
                candidate.setdefault("education", [])
                candidate.setdefault("donor_summary", None)
                candidate.setdefault("donor_source_url", None)
                candidate.setdefault("voting_summary", None)
                candidate.setdefault("voting_source_url", None)
                candidate.setdefault("links", [])
                candidate.setdefault("issues", {})
                active_candidates.append(candidate)
            if missing_evidence:
                return (
                    "ERROR: roster finalization blocked. These proposed candidates lack observed current-cycle "
                    f"exact-contest evidence: {', '.join(missing_evidence)}. Fetch or search sources that name them."
                )
        else:
            active_candidates = [
                candidate
                for candidate in race_json.get("candidates", [])
                if isinstance(candidate, dict) and candidate.get("name") and candidate.get("withdrawn") is not True
            ]
            if not active_candidates:
                return "ERROR: roster finalization blocked. Add at least one verified active candidate."
            missing_evidence = []
            for candidate in active_candidates:
                name = str(candidate.get("name") or "").strip()
                if not _qualifying_candidate_addition_sources(
                    candidate.get("roster_sources"),
                    candidate_name=name,
                    race_id=race_id,
                ):
                    missing_evidence.append(name)
            if missing_evidence:
                return (
                    "ERROR: roster finalization blocked. These active candidates lack durable current-cycle "
                    f"exact-contest roster evidence: {', '.join(missing_evidence)}. Search/fetch authoritative "
                    "sources, then call set_candidate_roster_sources or remove proven wrong-contest entries."
                )

        combined_evidence = " ".join(_roster_source_text(source) for source in qualifying_completeness)
        uncovered_names = []
        for candidate in active_candidates:
            name = str(candidate.get("name") or "").strip()
            name_words = re.findall(r"[a-z0-9]+", name.casefold())
            if not name_words or not all(word in combined_evidence for word in name_words):
                uncovered_names.append(name)
        if uncovered_names:
            return (
                "ERROR: roster finalization blocked. Completeness evidence does not name every active candidate: "
                f"{', '.join(uncovered_names)}. Quote the full authoritative list, not candidate-only excerpts."
            )

        if proposed_specs is not None:
            race_json["candidates"] = active_candidates

        summary = str(args.get("summary") or "").strip()
        pipeline_state = race_json.setdefault("pipeline_state", {})
        pipeline_state["roster_research"] = {
            "finalized_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "active_candidate_count": len(active_candidates),
            "completeness_sources": completeness_sources,
        }
        log("info", f"    Finalized roster with {len(active_candidates)} active candidate(s): {summary}")
        return f"Roster finalized with {len(active_candidates)} evidence-backed active candidate(s)."

    # --- Candidate field handlers ---

    def set_candidate_field(args: Dict[str, Any]) -> str:
        name, field, value = args["candidate_name"], args["field"], args["value"]
        if field not in _ALLOWED_CANDIDATE_FIELDS:
            return f"Field '{field}' not allowed. Allowed: {', '.join(sorted(_ALLOWED_CANDIDATE_FIELDS))}."
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        if field == "image_url" and value is not None and not _is_valid_image_url(value):
            log("warning", f"    Rejected non-image URL for {name}: {value!r}")
            return f"ERROR: {value!r} is not a direct image URL. " "Use a URL for an image file or set image_url to null."
        c[field] = value
        log("info", f"    {name}.{field} = {value!r}")
        return f"Set {name}.{field} = {value!r}."

    def set_candidate_summary(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["summary"] = args["summary"]
        if args.get("sources"):
            new_sources = [
                src for src in (_normalize_source(source, default_type="website") for source in args["sources"]) if src
            ]
            c["summary_sources"] = merge_source_lists(new_sources, c.get("summary_sources"))
        log("info", f"    Updated summary for {name}")
        return f"Updated summary for '{name}'."

    def finalize_metadata(args: Dict[str, Any]) -> str:
        """Apply the complete metadata payload only after all entries validate."""
        active_candidates = [
            candidate
            for candidate in race_json.get("candidates", [])
            if isinstance(candidate, dict) and candidate.get("name") and candidate.get("withdrawn") is not True
        ]
        proposed = args.get("candidates")
        if not isinstance(proposed, list) or not proposed:
            return "ERROR: metadata finalization requires every active candidate."
        active_names = {str(candidate["name"]).strip().casefold() for candidate in active_candidates}
        proposed_names = {str(item.get("name") or "").strip().casefold() for item in proposed if isinstance(item, dict)}
        if len(proposed_names) != len(proposed) or proposed_names != active_names:
            return "ERROR: metadata candidates must exactly match the complete active roster."

        description = str(args.get("description") or "").strip()
        description_sources = _normalize_observed_sources(
            args.get("description_sources"), args.get("_research_trace"), default_type="news"
        )
        if len(description) < 100 or not description_sources:
            return "ERROR: provide a substantive race description and at least one source observed during this research."

        validated: Dict[str, tuple[str, list[Dict[str, Any]]]] = {}
        for item in proposed:
            name = str(item.get("name") or "").strip()
            summary = str(item.get("summary") or "").strip()
            sources = _normalize_observed_sources(item.get("sources"), args.get("_research_trace"), default_type="website")
            if len(summary) < 80:
                return f"ERROR: summary for '{name}' is too thin; provide a factual 2-3 sentence biography."
            if not sources:
                return f"ERROR: summary for '{name}' needs a source URL observed during this research."
            validated[name.casefold()] = (summary, sources)

        # Atomic application: no mutation occurs until the entire submission passes.
        race_json["description"] = description
        for candidate in active_candidates:
            summary, sources = validated[str(candidate["name"]).strip().casefold()]
            candidate["summary"] = summary
            candidate["summary_sources"] = sources
        race_json.setdefault("pipeline_state", {})["metadata_research"] = {
            "finalized_at": datetime.now(timezone.utc).isoformat(),
            "active_candidate_count": len(active_candidates),
            "description_sources": description_sources,
            "candidate_sources": {item["name"]: validated[item["name"].strip().casefold()][1] for item in proposed},
        }
        log("info", f"    Finalized description and {len(active_candidates)} candidate summaries")
        return f"Metadata finalized for all {len(active_candidates)} active candidates."

    # --- Issue handler ---

    def set_issue_stance(args: Dict[str, Any]) -> str:
        from pipeline_client.agent.agent import _is_missing_stance_text

        name, issue = args["candidate_name"], args["issue"]
        if issue not in _CANONICAL_ISSUE_SET:
            close = get_close_matches(issue, CANONICAL_ISSUES, n=1, cutoff=0.4)
            hint = f" Did you mean: {close[0]!r}?" if close else f" Valid issues: {', '.join(CANONICAL_ISSUES)}."
            return f"ERROR: '{issue}' is not a canonical issue.{hint}"
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        stance_text = str(args["stance"] or "")
        if _is_missing_stance_text(stance_text) and "no public position found" not in stance_text.lower():
            log("warning", f"    set_issue_stance({name!r}, {issue!r}) BLOCKED: placeholder stance {stance_text!r}")
            return (
                f"ERROR: {stance_text!r} looks like a placeholder, not a real position. "
                "If no position was found after a good-faith search, use exactly "
                "'No public position found' with confidence 'low'."
            )
        existing_stance = c.get("issues", {}).get(issue)
        existing_sources = existing_stance.get("sources") if isinstance(existing_stance, dict) else []
        new_sources = [
            src for src in (_normalize_source(source, default_type="website") for source in args.get("sources") or []) if src
        ]
        merged_sources = merge_source_lists(new_sources, existing_sources)
        is_documented_absence = "no public position found" in stance_text.casefold()
        if not merged_sources and not is_documented_absence:
            return (
                f"ERROR: A substantive {issue} stance requires at least one supporting source. "
                "Provide sources, or record a documented absence with "
                "'No public position found'."
            )
        stance_data: Dict[str, Any] = {
            "stance": args["stance"],
            "confidence": args["confidence"],
            "sources": merged_sources,
        }
        c.setdefault("issues", {})[issue] = stance_data
        log("info", f"    {name} / {issue} [{args['confidence']}]")
        return f"Set {name}'s {issue} stance (confidence: {args['confidence']})."

    # --- Career, education, social media handlers ---

    def add_career_entry(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        entry = {
            "title": args["title"],
            "organization": args["organization"],
            "start_year": args.get("start_year"),
            "end_year": args.get("end_year"),
            "description": args.get("description", ""),
        }
        # Dedup: same org + overlapping years -> skip
        org_lower = args["organization"].lower()
        start = args.get("start_year")
        for existing in c.get("career_history", []):
            same_org = (
                org_lower in existing.get("organization", "").lower() or existing.get("organization", "").lower() in org_lower
            )
            same_start = existing.get("start_year") == start
            if same_org and same_start:
                return f"Career entry for '{args['organization']}' ({start}) already exists for '{name}' — skipping duplicate."
        c.setdefault("career_history", []).append(entry)
        log("info", f"    Added career entry for {name}: {args['title']} at {args['organization']}")
        return f"Added career entry for '{name}': {args['title']} at {args['organization']}."

    def add_education_entry(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        entry = {
            "institution": args["institution"],
            "degree": args["degree"],
            "field": args.get("field"),
            "year": args.get("year"),
        }
        # Dedup: same institution + degree -> skip
        inst_lower = args["institution"].lower()
        deg_lower = args["degree"].lower()
        for existing in c.get("education", []):
            if inst_lower in existing.get("institution", "").lower() and deg_lower in existing.get("degree", "").lower():
                return f"Education entry for '{args['institution']}' ({args['degree']}) already exists for '{name}' — skipping duplicate."
        c.setdefault("education", []).append(entry)
        log("info", f"    Added education for {name}: {args['degree']} from {args['institution']}")
        return f"Added education for '{name}': {args['degree']} from {args['institution']}."

    def set_social_media(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        platform = args["platform"].lower()
        c.setdefault("social_media", {})[platform] = args["url"]
        log("info", f"    {name}.social_media.{platform} = {args['url']}")
        return f"Set {name}'s {platform} to {args['url']}."

    def remove_career_entry(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        org = args["organization"].lower()
        before = len(c.get("career_history", []))
        c["career_history"] = [e for e in c.get("career_history", []) if org not in e.get("organization", "").lower()]
        removed = before - len(c["career_history"])
        log("info", f"    🗑️ Removed {removed} career entry/entries matching '{args['organization']}' for {name}")
        return f"Removed {removed} career entry/entries matching '{args['organization']}' for '{name}'."

    def update_career_entry(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        org = args["organization"].lower()
        matched = [e for e in c.get("career_history", []) if org in e.get("organization", "").lower()]
        if not matched:
            return f"No career entry matching '{args['organization']}' found for '{name}'."
        for entry in matched:
            for field in ("title", "start_year", "end_year", "description"):
                if field in args:
                    entry[field] = args[field]
        changes = {k: v for k, v in args.items() if k not in ("candidate_name", "organization")}
        log("info", f"    ✏️ Updated career entry '{args['organization']}' for {name}: {changes}")
        return f"Updated {len(matched)} career entry/entries for '{name}' matching '{args['organization']}'."

    def update_education_entry(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        inst = args["institution"].lower()
        matched = [e for e in c.get("education", []) if inst in e.get("institution", "").lower()]
        if not matched:
            return f"No education entry matching '{args['institution']}' found for '{name}'."
        for entry in matched:
            for field in ("degree", "field", "year"):
                if field in args:
                    entry[field] = args[field]
        changes = {k: v for k, v in args.items() if k not in ("candidate_name", "institution")}
        log("info", f"    ✏️ Updated education entry '{args['institution']}' for {name}: {changes}")
        return f"Updated {len(matched)} education entry/entries for '{name}' matching '{args['institution']}'."

    def clear_career_history(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["career_history"] = []
        log("info", f"    🗑️ Cleared career_history for {name}")
        return f"Cleared career_history for '{name}'. Use add_career_entry to add correct entries."

    def clear_education(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["education"] = []
        log("info", f"    🗑️ Cleared education for {name}")
        return f"Cleared education for '{name}'. Use add_education_entry to add correct entries."

    # --- Record handlers (summary setters) ---

    def set_donor_summary(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["donor_summary"] = args["summary"]
        if args.get("source_url"):
            c["donor_source_url"] = args["source_url"]
        if isinstance(args.get("sources"), list):
            new_sources = [src for src in (_normalize_source(s) for s in args["sources"]) if src]
            c["donor_sources"] = merge_source_lists(new_sources, c.get("donor_sources"))
        log("info", f"    Updated donor summary for {name}")
        return f"Updated donor summary for '{name}'."

    def set_voting_summary(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["voting_summary"] = args["summary"]
        if args.get("source_url"):
            c["voting_source_url"] = args["source_url"]
        if isinstance(args.get("sources"), list):
            new_sources = [src for src in (_normalize_source(s) for s in args["sources"]) if src]
            c["voting_sources"] = merge_source_lists(new_sources, c.get("voting_sources"))
        log("info", f"    Updated voting summary for {name}")
        return f"Updated voting summary for '{name}'."

    def add_candidate_link(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        url = args["url"]
        existing_urls = {lnk.get("url") for lnk in c.get("links", []) if isinstance(lnk, dict)}
        if url in existing_urls:
            return f"Link already exists for '{name}': {url}"
        c.setdefault("links", []).append(
            {
                "url": url,
                "title": args["title"],
                "type": args.get("type", "other"),
            }
        )
        log("info", f"    🔗 Added link for {name}: {url[:60]}")
        return f"Added {args.get('type', 'other')} link for '{name}'."

    def remove_candidate_source_url(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        url = str(args["url"]).strip()
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        if not url:
            return "ERROR: url is required."

        removed = 0

        def _remove_from_source_list(key: str) -> None:
            nonlocal removed
            items = c.get(key)
            if not isinstance(items, list):
                return
            kept = [item for item in items if not (isinstance(item, dict) and item.get("url") == url)]
            removed += len(items) - len(kept)
            c[key] = kept

        for list_key in ("summary_sources", "donor_sources", "voting_sources", "links"):
            _remove_from_source_list(list_key)

        for scalar_key in ("donor_source_url", "voting_source_url"):
            if c.get(scalar_key) == url:
                c[scalar_key] = None
                removed += 1

        issues = c.get("issues")
        if isinstance(issues, dict):
            for issue_data in issues.values():
                if not isinstance(issue_data, dict):
                    continue
                sources = issue_data.get("sources")
                if not isinstance(sources, list):
                    continue
                kept = [source for source in sources if not (isinstance(source, dict) and source.get("url") == url)]
                removed += len(sources) - len(kept)
                issue_data["sources"] = kept

        pipeline_state = race_json.setdefault("pipeline_state", {})
        removals = pipeline_state.setdefault("removed_source_urls", [])
        tombstone = {"candidate_name": name, "url": url}
        if not any(
            isinstance(item, dict)
            and str(item.get("candidate_name") or "").strip().casefold() == name.strip().casefold()
            and str(item.get("url") or "").strip() == url
            for item in removals
        ):
            removals.append(tombstone)

        log("info", f"    Removed {removed} occurrence(s) of source URL for {name}: {url[:80]}")
        return f"Removed {removed} occurrence(s) of {url!r} from '{name}'."

    # --- Race-level handlers ---

    def add_poll(args: Dict[str, Any]) -> str:
        roster_names = {
            str(candidate.get("name") or "").strip()
            for candidate in race_json.get("candidates", [])
            if isinstance(candidate, dict) and str(candidate.get("name") or "").strip()
        }
        matchups = args.get("matchups")
        if not isinstance(matchups, list):
            return "ERROR: Poll matchups must be a list. Use an empty list only when the source does not publish numbers."

        matchup_names = set()
        for index, matchup in enumerate(matchups):
            if not isinstance(matchup, dict):
                return f"ERROR: Poll matchup {index + 1} must be an object with candidates and percentages."
            candidates = matchup.get("candidates")
            percentages = matchup.get("percentages")
            if not isinstance(candidates, list) or not candidates:
                return f"ERROR: Poll matchup {index + 1} must include candidate names."
            if not isinstance(percentages, list) or not percentages:
                return f"ERROR: Poll matchup {index + 1} must include numeric percentages."
            if len(candidates) != len(percentages):
                return f"ERROR: Poll matchup {index + 1} candidates and percentages must have the same length."
            for percentage in percentages:
                if not isinstance(percentage, (int, float)) or not 0 <= percentage <= 100:
                    return f"ERROR: Poll matchup {index + 1} has an invalid percentage value: {percentage!r}."
            matchup_names.update(str(name).strip() for name in candidates if str(name).strip())

        unknown_names = sorted(matchup_names - roster_names)
        if unknown_names:
            return (
                "ERROR: Poll matchup candidate names must exactly match the current roster. "
                f"Unknown names: {', '.join(unknown_names)}. Valid names: {', '.join(sorted(roster_names))}."
            )
        poll = {
            "pollster": args["pollster"],
            "date": args["date"],
            "matchups": matchups,
            "source_url": args["source_url"],
        }
        if args.get("sample_size"):
            poll["sample_size"] = args["sample_size"]
        semantic_problem = polling_semantic_problem(poll, race_json.get("polling_note"))
        if semantic_problem:
            return f"ERROR: {semantic_problem}"
        # Dedup: same pollster + date
        for existing in race_json.get("polling", []):
            if existing.get("pollster") == args["pollster"] and existing.get("date") == args["date"]:
                return f"Poll from {args['pollster']} ({args['date']}) already exists — skipping duplicate."
        race_json.setdefault("polling", []).insert(0, poll)
        log("info", f"    📊 Added poll: {args['pollster']} ({args['date']})")
        return f"Added poll from {args['pollster']} ({args['date']})."

    def remove_poll(args: Dict[str, Any]) -> str:
        pollster = args["pollster"]
        date = args.get("date")
        reason = args.get("reason", "")
        if re.search(
            r"\b(?:roster alignment|did not include|does not include|missing from (?:the )?matchup|"
            r"subset of (?:the )?(?:full )?roster)\b",
            str(reason),
            re.IGNORECASE,
        ):
            return (
                "ERROR: Poll removal blocked. A primary or partial-matchup poll is valid when every named person "
                "belongs to the roster; it must not include every candidate or the other party. Remove only a "
                "duplicate, malformed record, non-poll result, or poll proven to concern a different contest."
            )
        polling = race_json.get("polling", [])
        orig_len = len(polling)
        if date:
            race_json["polling"] = [p for p in polling if not (p.get("pollster") == pollster and p.get("date") == date)]
            removed = orig_len - len(race_json["polling"])
            if removed:
                log("info", f"    🗑️ Removed poll: {pollster} ({date}) — {reason}")
                return f"Removed {removed} poll(s) from {pollster} ({date})."
            return f"No poll found matching {pollster} / {date} — no action taken."
        else:
            race_json["polling"] = [p for p in polling if p.get("pollster") != pollster]
            removed = orig_len - len(race_json["polling"])
            if removed:
                log("info", f"    🗑️ Removed {removed} poll(s) by '{pollster}' — {reason}")
                return f"Removed {removed} poll(s) from {pollster}."
            return f"No polls found for pollster '{pollster}' — no action taken."

    def update_race_field(args: Dict[str, Any]) -> str:
        field, value = args["field"], args["value"]
        if field not in _ALLOWED_RACE_FIELDS:
            return f"Field '{field}' not allowed. Allowed: {', '.join(sorted(_ALLOWED_RACE_FIELDS))}."
        if field == "contest_stage":
            value = str(value or "unknown").strip().lower()
            if value not in _CONTEST_STAGES:
                return f"ERROR: contest_stage must be one of: {', '.join(sorted(_CONTEST_STAGES))}."
        if field == "ballotpedia_url":
            default_url = default_ballotpedia_race_url(str(race_json.get("id") or ""))
            if default_url and "_Congressional_District" in default_url and "ballotpedia.org" in str(value):
                value = default_url
        if field == "description":
            from .review import is_substantive_race_description

            if not is_substantive_race_description(value, race_json.get("title")):
                log("warning", "    Rejected low-information race description")
                return (
                    "ERROR: Race description must be a substantive 3-4 sentence overview covering the office, "
                    "candidates, political context, and key contrasts. Do not repeat the race title."
                )
        race_json[field] = value
        log("info", f"    race.{field} updated")
        return f"Updated race.{field}."

    def set_forecast(args: Dict[str, Any]) -> str:
        rating = args["rating"]
        if rating not in {
            "safe_d",
            "likely_d",
            "lean_d",
            "tilt_d",
            "tossup",
            "tilt_r",
            "lean_r",
            "likely_r",
            "safe_r",
            "other",
        }:
            return f"ERROR: Forecast rating '{rating}' is not valid."
        confidence = args["confidence"]
        if confidence not in {"high", "medium", "low", "unknown"}:
            return f"ERROR: Forecast confidence '{confidence}' is not valid."

        predicted_winner_name = str(args.get("predicted_winner_name") or "").strip()
        if predicted_winner_name:
            active_names = {
                str(candidate.get("name") or "").strip().casefold()
                for candidate in race_json.get("candidates", [])
                if isinstance(candidate, dict) and not candidate.get("withdrawn")
            }
            if predicted_winner_name.casefold() not in active_names:
                return f"ERROR: Forecast winner '{predicted_winner_name}' is not in the active candidate roster."

        def _optional_probability(value: Any, field_name: str) -> float | None:
            if value in (None, ""):
                return None
            if not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
                raise ValueError(f"{field_name} must be a number from 0 to 1")
            return float(value)

        try:
            win_probability = _optional_probability(args.get("win_probability"), "win_probability")
            party_probabilities = {}
            for party, probability in (args.get("party_probabilities") or {}).items():
                normalized = _optional_probability(probability, f"party_probabilities[{party}]")
                if normalized is not None:
                    party_probabilities[str(party)] = normalized
        except ValueError as exc:
            return f"ERROR: {exc}"

        if win_probability is None:

            def _party_key(value: Any) -> str:
                key = str(value or "").strip().casefold()
                if key.endswith(" party"):
                    key = key[: -len(" party")].strip()
                return {"democrat": "democratic", "gop": "republican"}.get(key, key)

            predicted_party = _party_key(args.get("predicted_winner_party"))
            matching_probability = next(
                (
                    probability
                    for party, probability in party_probabilities.items()
                    if predicted_party and predicted_party == _party_key(party)
                ),
                None,
            )
            if matching_probability is not None:
                win_probability = matching_probability

        predicted_winner_party = args.get("predicted_winner_party")
        if isinstance(predicted_winner_party, str):
            predicted_winner_party = predicted_winner_party.strip()
        if not predicted_winner_party:
            if rating == "tossup":
                predicted_winner_party = "Toss-up"
            elif party_probabilities:
                max_party = max(party_probabilities.keys(), key=lambda k: party_probabilities[k])
                max_prob = party_probabilities[max_party]
                ties = [k for k, v in party_probabilities.items() if v == max_prob]
                if len(ties) == 1:
                    predicted_winner_party = max_party
                else:
                    incumbent = next(
                        (c for c in race_json.get("candidates", []) if isinstance(c, dict) and c.get("incumbent")), None
                    )
                    if incumbent and incumbent.get("party"):
                        inc_party = str(incumbent["party"]).lower()
                        if "democrat" in inc_party or inc_party == "d":
                            predicted_winner_party = "Democratic"
                        elif "republican" in inc_party or inc_party == "r":
                            predicted_winner_party = "Republican"

        forecast = {
            "predicted_winner_name": predicted_winner_name or None,
            "predicted_winner_party": predicted_winner_party or None,
            "win_probability": win_probability,
            "party_probabilities": party_probabilities,
            "margin_estimate": args.get("margin_estimate"),
            "rating": rating,
            "confidence": confidence,
            "rationale": str(args.get("rationale") or "").strip(),
            "takeaway": str(args.get("takeaway") or "").strip() or None,
            "key_reasons": [str(reason).strip() for reason in args.get("key_reasons") or [] if str(reason).strip()],
            "uncertainty": str(args.get("uncertainty") or "").strip() or None,
            "based_on_poll_count": max(0, int(args.get("based_on_poll_count") or 0)),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": str(args.get("model") or ""),
            "source_urls": [str(url) for url in args.get("source_urls") or [] if str(url).strip()],
            "evidence_lineage": [
                {
                    "claim": str(item.get("claim") or "").strip(),
                    "source_url": str(item.get("source_url") or "").strip(),
                    "kind": str(item.get("kind") or "other"),
                    "inferred": bool(item.get("inferred", False)),
                }
                for item in args.get("evidence_lineage") or []
                if isinstance(item, dict)
                and str(item.get("claim") or "").strip()
                and str(item.get("source_url") or "").strip()
            ],
        }
        race_json["forecast"] = forecast
        log("info", f"    race.forecast updated ({rating})")
        return "Updated race.forecast."

    # --- Read-only verification handler ---

    def read_profile(args: Dict[str, Any]) -> str:
        section = args.get("section", "full")
        if section == "full":
            return json.dumps(race_json, separators=(",", ":"), default=str)
        if section == "candidates":
            return json.dumps(race_json.get("candidates", []), separators=(",", ":"), default=str)
        if section == "candidate":
            candidate_name = str(args.get("candidate_name") or "").strip().lower()
            for candidate in race_json.get("candidates", []):
                if str(candidate.get("name") or "").strip().lower() == candidate_name:
                    return json.dumps(candidate, separators=(",", ":"), default=str)
            return f"Candidate '{args.get('candidate_name', '')}' not found."
        if section == "issues":
            compact = {}
            for c in race_json.get("candidates", []):
                issues = {}
                for k, v in c.get("issues", {}).items():
                    if isinstance(v, dict):
                        issues[k] = {
                            "stance": v.get("stance", "")[:80],
                            "confidence": v.get("confidence", "?"),
                        }
                compact[c.get("name", "?")] = issues
            return json.dumps(compact, separators=(",", ":"))
        if section == "polling":
            return json.dumps(race_json.get("polling", []), separators=(",", ":"), default=str)
        if section == "forecast":
            return json.dumps(race_json.get("forecast"), separators=(",", ":"), default=str)
        if section == "meta":
            return json.dumps(
                {
                    k: race_json.get(k)
                    for k in ("id", "title", "office", "jurisdiction", "election_date", "description")
                    if k in race_json
                },
                separators=(",", ":"),
                default=str,
            )
        return f"Unknown section '{section}'."

    handlers: Dict[str, Any] = {
        "add_candidate": add_candidate,
        "remove_candidate": remove_candidate,
        "rename_candidate": rename_candidate,
        "set_candidate_roster_sources": set_candidate_roster_sources,
        "set_race_identity": set_race_identity,
        "finalize_roster": finalize_roster,
        "set_candidate_field": set_candidate_field,
        "set_candidate_summary": set_candidate_summary,
        "finalize_metadata": finalize_metadata,
        "set_issue_stance": set_issue_stance,
        "set_donor_summary": set_donor_summary,
        "set_voting_summary": set_voting_summary,
        "add_candidate_link": add_candidate_link,
        "remove_candidate_source_url": remove_candidate_source_url,
        "add_poll": add_poll,
        "remove_poll": remove_poll,
        "update_race_field": update_race_field,
        "set_forecast": set_forecast,
        "read_profile": read_profile,
        "add_career_entry": add_career_entry,
        "remove_career_entry": remove_career_entry,
        "update_career_entry": update_career_entry,
        "add_education_entry": add_education_entry,
        "update_education_entry": update_education_entry,
        "set_social_media": set_social_media,
        "clear_career_history": clear_career_history,
        "clear_education": clear_education,
    }

    if restrict_to_candidate:
        # Tools that mutate an *existing* candidate's data by name. Roster-membership
        # tools (add_candidate — no existing target to mismatch) and race-wide tools
        # (set_race_identity, update_race_field, set_forecast, add/remove_poll) are
        # intentionally excluded; read_profile is read-only.
        _scoped_tool_names = {
            "remove_candidate",
            "rename_candidate",
            "set_candidate_roster_sources",
            "set_candidate_field",
            "set_candidate_summary",
            "set_issue_stance",
            "set_donor_summary",
            "set_voting_summary",
            "add_candidate_link",
            "remove_candidate_source_url",
            "add_career_entry",
            "remove_career_entry",
            "update_career_entry",
            "add_education_entry",
            "update_education_entry",
            "set_social_media",
            "clear_career_history",
            "clear_education",
        }

        def _scope_guard(tool_name: str, handler: Callable) -> Callable:
            def _guarded(args: Dict[str, Any]) -> str:
                target = args.get("candidate_name")
                if target and target != restrict_to_candidate:
                    log(
                        "warning",
                        f"    {tool_name}(candidate_name={target!r}) BLOCKED — this turn is scoped "
                        f"to {restrict_to_candidate!r} only",
                    )
                    return (
                        f"ERROR: This turn may only edit '{restrict_to_candidate}'. "
                        f"Call {tool_name} with candidate_name={restrict_to_candidate!r}, or skip this edit."
                    )
                return handler(args)

            return _guarded

        for tool_name in _scoped_tool_names:
            handlers[tool_name] = _scope_guard(tool_name, handlers[tool_name])

    return handlers
