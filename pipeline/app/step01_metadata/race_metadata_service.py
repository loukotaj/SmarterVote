"""
Race Metadata Extraction Service for SmarterVote Pipeline (v0.6)

"""

from __future__ import annotations

import json
import logging
import re
import time
import traceback
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from shared.state_constants import PRIMARY_DATE_BY_STATE, STATE_NAME

from ..providers.base import ProviderRegistry, TaskType
from ..schema import DiscoveredCandidate  # if your schema exposes this
from ..schema import ConfidenceLevel, FreshSearchQuery, RaceMetadata, Source, SourceType
from ..step03_fetch import WebContentFetcher
from ..step04_extract import ContentExtractor
from ..utils.search_utils import SearchUtils

logger = logging.getLogger(__name__)

# --------------------------- constants & regex --------------------------- #

TRUSTED_DOMAINS = {"ballotpedia.org", "wikipedia.org", "fec.gov", "vote411.org"}

SLUG_PATTERN = re.compile(
    r"^(?P<state>[a-z]{2})-(?P<office>[a-z]+(?:-[a-z]+)*?)"  # e.g., mo-senate, ny-house, ca-secretary-state
    r"(?:-(?P<district>\d{1,2}|al))?-(?P<year>\d{4})"  # optional district: 01..99 or al
    r"(?:-(?P<kind>primary|runoff|special))?$",
)

# Names we should never treat as candidates
NAME_STOP_WORDS = {
    "united states",
    "candidate connection",
    "republican party",
    "democratic party",
    "state senate",
    "state house",
    "missouri state",
    "u.s.",
    "us senate",
    "u.s. senate",
    "house of representatives",
}

PARTY_ALIASES = {
    "d": "Democratic",
    "democrat": "Democratic",
    "democratic": "Democratic",
    "r": "Republican",
    "republican": "Republican",
    "i": "Independent",
    "independent": "Independent",
    "l": "Libertarian",
    "libertarian": "Libertarian",
    "g": "Green",
    "green": "Green",
    "np": "Nonpartisan",
    "npp": "Nonpartisan",
    "u": "Unaffiliated",
    "unaffiliated": "Unaffiliated",
}

# --------------------------- logging helpers --------------------------- #


def _now_utc_iso() -> str:
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def _jlog(level: int, event: str, trace_id: str, **fields: Any) -> None:
    payload = {
        "ts": _now_utc_iso(),
        "level": logging.getLevelName(level).lower(),
        "event": event,
        "trace_id": trace_id,
        "component": "RaceMetadataService",
        **fields,
    }
    try:
        logger.log(level, json.dumps(payload, default=str))
    except Exception:
        logger.log(level, f"{event} | trace_id={trace_id} | {fields}")


def _exc_fields(e: Exception) -> Dict[str, Any]:
    return {
        "error": str(e),
        "error_class": e.__class__.__name__,
        "error_code": getattr(e, "code", None),
        "error_details": getattr(e, "details", None),
        "stack": "".join(traceback.format_exc(limit=2)).strip(),
    }


# --------------------------- main service --------------------------- #


class RaceMetadataService:
    """Metadata extraction orchestrator for a single race_id."""

    def __init__(self, providers: Optional[ProviderRegistry] = None) -> None:
        self.providers = providers

        # Keep search simple & deterministic for now
        self.search = SearchUtils(
            {
                "max_results_per_query": 10,
                "per_host_concurrency": 5,
            }
        )
        self.fetcher = WebContentFetcher()
        self.extractor = ContentExtractor()

        # Office mappings → display + defaults
        self.office_mappings = {
            "senate": {
                "full_name": "U.S. Senate",
                "race_type": "federal",
                "term_years": 6,
                "major_issues": ["Healthcare", "Economy", "Foreign Policy", "Climate/Energy"],
            },
            "house": {
                "full_name": "U.S. House of Representatives",
                "race_type": "federal",
                "term_years": 2,
                "major_issues": ["Healthcare", "Economy", "Education", "Immigration"],
            },
            "governor": {
                "full_name": "Governor",
                "race_type": "state",
                "term_years": 4,
                "major_issues": ["Economy", "Education", "Healthcare", "Climate/Energy"],
            },
            "lt-governor": {
                "full_name": "Lieutenant Governor",
                "race_type": "state",
                "term_years": 4,
                "major_issues": ["Economy", "Education", "Social Justice"],
            },
            "attorney-general": {
                "full_name": "Attorney General",
                "race_type": "state",
                "term_years": 4,
                "major_issues": ["Guns & Safety", "Social Justice", "Election Reform"],
            },
            "secretary-state": {
                "full_name": "Secretary of State",
                "race_type": "state",
                "term_years": 4,
                "major_issues": ["Election Reform", "Tech & AI"],
            },
        }

    # ---------------------- public API ---------------------- #

    async def extract_race_metadata(self, race_id: str) -> RaceMetadata:
        trace_id = uuid.uuid4().hex
        t0 = time.perf_counter()
        _jlog(logging.INFO, "race_metadata.extract.start", trace_id, race_id=race_id)

        try:
            state, office_type, year, district, kind = self._parse_race_id(race_id, trace_id)
            is_primary = kind == "primary"

            office_info = self._get_office_info(office_type)
            election_date = self._calculate_election_date(year)
            primary_date = self._get_primary_date(state, year) if is_primary else None
            jurisdiction = self._build_jurisdiction(state, district)
            major_issues = self._get_major_issues(office_type)
            geographic_keywords = self._geo_keywords(state, district)

            # Phase 1: strict (trusted domains)
            strict = await self._discover(race_id, state, office_type, year, district, trace_id, strict=True)

            # Phase 2: fallback (if strict empty)
            cands = strict
            if not cands:
                _jlog(logging.INFO, "candidate_discovery.fallback.start", trace_id, reason="strict_yielded_zero")
                cands = await self._discover(race_id, state, office_type, year, district, trace_id, strict=False)
                _jlog(logging.INFO, "candidate_discovery.fallback.finish", trace_id, found=len(cands))

            # Optional AI pass to clean names/parties
            cands = await self._ai_refine_candidates(cands, race_id, state, office_type, year, district, trace_id)

            incumbent_party = self._incumbent_party(cands)
            confidence = self._confidence(cands, bool(primary_date), trace_id)

            # Final JSON-safe candidates
            cands = self._sanitize_candidates_for_json(cands)

            meta = RaceMetadata(
                race_id=race_id,
                state=state,
                office_type=office_type,
                year=year,
                full_office_name=office_info["full_name"],
                jurisdiction=jurisdiction,
                district=district,
                election_date=election_date,
                race_type=office_info["race_type"],
                is_primary=is_primary,
                primary_date=primary_date,
                is_special_election=(kind == "special"),
                is_runoff=(kind == "runoff"),
                discovered_candidates=[c.name for c in cands],
                structured_candidates=cands,
                incumbent_party=incumbent_party,
                major_issues=major_issues,
                geographic_keywords=geographic_keywords,
                confidence=confidence,
            )

            _jlog(
                logging.INFO,
                "race_metadata.extract.success",
                trace_id,
                race_id=race_id,
                candidates=len(cands),
                confidence=str(confidence.value),
                total_duration_ms=int((time.perf_counter() - t0) * 1000),
            )
            return meta
        except Exception as e:  # keep the pipeline alive with a fallback shell
            _jlog(
                logging.ERROR,
                "race_metadata.extract.error",
                trace_id,
                race_id=race_id,
                **_exc_fields(e),
                total_duration_ms=int((time.perf_counter() - t0) * 1000),
            )
            # Minimal viable metadata on error
            return RaceMetadata(
                race_id=race_id,
                state=race_id.split("-")[0].upper() if "-" in race_id else "",
                office_type=race_id.split("-")[1] if len(race_id.split("-")) > 1 else "",
                year=int(race_id.split("-")[-1]) if race_id.split("-")[-1].isdigit() else datetime.utcnow().year,
                full_office_name=self._get_office_info(race_id.split("-")[1] if "-" in race_id else "")["full_name"],
                jurisdiction=race_id.split("-")[0].upper() if "-" in race_id else "",
                district=None,
                election_date=self._calculate_election_date(datetime.utcnow().year),
                race_type=self._get_office_info(race_id.split("-")[1] if "-" in race_id else "")["race_type"],
                is_primary=False,
                primary_date=None,
                is_special_election=False,
                is_runoff=False,
                discovered_candidates=[],
                structured_candidates=[],
                incumbent_party=None,
                major_issues=self._get_major_issues(race_id.split("-")[1] if "-" in race_id else ""),
                geographic_keywords=[],
                confidence=ConfidenceLevel.LOW,
            )

    # ---------------------- discovery ---------------------- #

    async def _discover(
        self,
        race_id: str,
        state: str,
        office_type: str,
        year: int,
        district: Optional[str],
        trace_id: str,
        strict: bool,
    ) -> List[DiscoveredCandidate]:
        phase = "strict" if strict else "fallback"

        # 1) Build queries
        if strict:
            queries = self._queries_strict(race_id, state, office_type, year, district)
        else:
            queries = self._queries_fallback(race_id, state, office_type, year, district)

        _jlog(
            logging.INFO,
            f"candidate_discovery.{phase}.queries",
            trace_id,
            count=len(queries),
            sample=[q.text for q in queries[:3]],
        )

        # 2) Search
        results: List[Source] = []
        errors = 0
        for i, q in enumerate(queries):
            t = time.perf_counter()
            try:
                res = await self.search.search_general(q)
                results.extend(res or [])
                _jlog(
                    logging.DEBUG,
                    f"candidate_discovery.{phase}.query.results",
                    trace_id,
                    idx=i,
                    text=q.text[:160],
                    results=len(res or []),
                    duration_ms=int((time.perf_counter() - t) * 1000),
                )
            except Exception as e:
                errors += 1
                _jlog(
                    logging.WARNING,
                    f"candidate_discovery.{phase}.query.error",
                    trace_id,
                    idx=i,
                    text=q.text[:160],
                    **_exc_fields(e),
                )

        if not results:
            if strict and errors:
                # On strict failure, escalate to fallback immediately
                _jlog(logging.INFO, "candidate_discovery.fallback.start", trace_id, reason="strict_errors")
                return await self._discover(race_id, state, office_type, year, district, trace_id, strict=False)

            # Last-chance canonical URLs
            last_urls = self._last_chance_urls(state, office_type, year, district)
            if last_urls:
                try:
                    _jlog(logging.INFO, "candidate_discovery.last_chance.start", trace_id, urls=last_urls[:5])
                    fetched = await self.fetcher.fetch_content([Source(url=u, type=SourceType.WEBSITE) for u in last_urls])
                    extracted = await self.extractor.extract_content(fetched)
                    harvested = self._harvest_from_extractions(extracted, trace_id)
                    return self._merge_and_dedupe(harvested)
                except Exception as e:
                    _jlog(logging.WARNING, "candidate_discovery.last_chance.error", trace_id, **_exc_fields(e))
            _jlog(logging.WARNING, f"candidate_discovery.{phase}.no_results", trace_id)
            return []

        # 3) Prefilter + cap
        filtered = self._prefilter_sources(results, strict)
        _jlog(logging.INFO, f"candidate_discovery.{phase}.prefiltered", trace_id, before=len(results), after=len(filtered))

        # 4) Fetch
        fetched = await self.fetcher.fetch_content(filtered)
        ok = sum(1 for f in fetched if getattr(f, "ok", True))
        hosts: Dict[str, int] = {}
        for item in fetched:
            try:
                host = urlparse(str(getattr(item, "final_url", getattr(item, "url", "")))).netloc.replace("www.", "")
                if host:
                    hosts[host] = hosts.get(host, 0) + 1
            except Exception:
                pass
        _jlog(
            logging.INFO,
            f"candidate_discovery.{phase}.fetched",
            trace_id,
            count=len(fetched),
            ok=ok,
            top_hosts=sorted(hosts.items(), key=lambda x: -x[1])[:5],
        )
        if not fetched:
            return []

        # 5) Extract
        extracted = await self.extractor.extract_content(fetched)
        usable = sum(1 for e in extracted if getattr(e, "text", None))
        _jlog(logging.INFO, f"candidate_discovery.{phase}.extracted", trace_id, count=len(extracted), usable=usable)
        if not extracted:
            return []

        # 6) Harvest from extracted text and from search snippets (trusted only)
        c_from_text = self._harvest_from_extractions(extracted, trace_id)
        c_from_snip = self._harvest_from_snippets(filtered, trace_id)
        merged = self._merge_and_dedupe(c_from_text + c_from_snip)
        return merged

    # ---------------------- query builders ---------------------- #

    def _queries_strict(
        self, race_id: str, state: str, office: str, year: int, district: Optional[str]
    ) -> List[FreshSearchQuery]:
        queries: List[FreshSearchQuery] = []
        full_office = self._get_office_info(office)["full_name"]
        state_name = STATE_NAME.get(state, state)

        district_text = ""
        if district:
            district_text = (
                " at-large" if district == "AL" else f" district {int(district) if district.isdigit() else district}"
            )

        terms = [
            f"site:ballotpedia.org {year} {state_name}{district_text} {office} election",
            f"site:ballotpedia.org {state_name} {full_office} {year} candidates",
            f"site:wikipedia.org {year} {state_name}{district_text} {office} election",
        ]
        if office in {"senate", "house"}:
            terms.append(f"site:fec.gov {year} {state} {office} candidates")

        for t in terms:
            queries.append(FreshSearchQuery(race_id=race_id, text=t, max_results=10, date_restrict="y2"))
        return queries

    def _queries_fallback(
        self, race_id: str, state: str, office: str, year: int, district: Optional[str]
    ) -> List[FreshSearchQuery]:
        queries: List[FreshSearchQuery] = []
        state_name = STATE_NAME.get(state, state)
        district_text = (
            " at-large" if district == "AL" else (f" district {int(district)}" if district and district.isdigit() else "")
        )
        base = f"{year} {state_name}{district_text} {office}"
        for t in [
            f"{base} candidates",
            f"{base} candidate list",
            f"{base} ballotpedia OR wikipedia OR site:.gov",
            f"{base} official campaign website",
            f"{base} filed candidates",
            f"{base} primary candidates",
        ]:
            queries.append(FreshSearchQuery(race_id=race_id, text=t, max_results=10, date_restrict="y2"))
        return queries

    def _last_chance_urls(self, state: str, office: str, year: int, district: Optional[str]) -> List[str]:
        urls: List[str] = []
        state_ = STATE_NAME.get(state, state).replace(" ", "_")
        if office == "senate":
            urls += [
                f"https://en.wikipedia.org/wiki/{year}_United_States_Senate_election_in_{state_}",
                f"https://ballotpedia.org/{year}_United_States_Senate_election_in_{state_}",
                f"https://www.fec.gov/data/candidates/senate/?election_year={year}&state={state}",
            ]
        elif office == "house":
            base = f"https://en.wikipedia.org/wiki/{year}_United_States_House_of_Representatives_elections_in_{state_}"
            if district == "AL":
                urls.append(base + "#At-large")
            elif district and district.isdigit():
                urls.append(base + f"#District_{int(district)}")
            else:
                urls.append(base)
            fec = f"https://www.fec.gov/data/candidates/house/?election_year={year}&state={state}"
            if district and district.isdigit():
                fec += f"&district={int(district)}"
            urls.append(fec)
        return urls

    # ---------------------- fetch/extract helpers ---------------------- #

    def _prefilter_sources(self, sources: List[Source], strict: bool) -> List[Source]:
        seen: set[str] = set()
        out: List[Source] = []
        for s in sources:
            url = str(getattr(s, "url", "")).strip()
            if not url or url in seen:
                continue
            seen.add(url)
            if strict and not self._is_trusted(url):
                continue
            out.append(s)

        def key_fn(src: Source):  # trusted first, then recency desc
            host = urlparse(str(src.url)).netloc.replace("www.", "")
            is_trusted = any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS)
            ts = getattr(src, "published_at", None)
            return (0 if is_trusted else 1, -int(ts.timestamp()) if ts else 0)

        out.sort(key=key_fn)
        return out[:18]

    def _harvest_from_extractions(self, extracted: List[Any], trace_id: str) -> List[DiscoveredCandidate]:
        cands: List[DiscoveredCandidate] = []
        for item in extracted:
            try:
                text = getattr(item, "text", "") or ""
                meta = getattr(item, "metadata", {}) or {}
                src = getattr(item, "source", None)
                source_url = (
                    str(getattr(src, "url", "")) if src else (meta.get("final_url") or meta.get("canonical_url") or "")
                )

                names = (meta.get("entity_hits", {}) or {}).get("candidates") or []
                if not names:
                    names = self._regex_scan_names(text)

                for name in names:
                    if not self._looks_like_person(name):
                        continue
                    party = self._party_from_context(text, name)
                    incumbent = self._is_incumbent(text, name)
                    cands.append(
                        DiscoveredCandidate(
                            name=name.strip(),
                            party=party,
                            incumbent=incumbent,
                            sources=[self._norm_url(source_url)] if source_url else [],
                        )
                    )
            except Exception as e:
                _jlog(logging.DEBUG, "harvest.from_extraction.error", trace_id, **_exc_fields(e))
        _jlog(logging.INFO, "harvest.from_extraction.done", trace_id, candidates=len(cands))
        return cands

    def _harvest_from_snippets(self, results: List[Source], trace_id: str) -> List[DiscoveredCandidate]:
        cands: List[DiscoveredCandidate] = []
        patts = [
            # Name (Party)
            r"([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s*\((?P<party>[A-Za-z]{1,15})\)",
            # Incumbent Name (R/D/...) variants
            r"(?:Incumbent|Senator|Representative|Rep\.)\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\s*\((?P<party>[A-Za-z]{1,15})\)",
        ]
        trusted_only = [s for s in results if self._is_trusted(str(getattr(s, "url", "")))]
        for s in trusted_only:
            blob = f"{getattr(s, 'title', '')} {getattr(s, 'description', '')}"
            for p in patts:
                for m in re.finditer(p, blob):
                    name = m.group(1).strip()
                    party = self._normalize_party(m.groupdict().get("party"))
                    if self._looks_like_person(name):
                        cands.append(
                            DiscoveredCandidate(name=name, party=party, incumbent=False, sources=[self._norm_url(str(s.url))])
                        )
        _jlog(logging.DEBUG, "candidates.extracted_from_snippets", trace_id, extracted=len(cands))
        return cands

    # ---------------------- AI refinement (optional) ---------------------- #

    async def _ai_refine_candidates(
        self,
        candidates: List[DiscoveredCandidate],
        race_id: str,
        state: str,
        office: str,
        year: int,
        district: Optional[str],
        trace_id: str,
    ) -> List[DiscoveredCandidate]:
        if not candidates:
            return []
        if not self.providers:
            return self._merge_and_dedupe(candidates)
        try:
            # Compose a compact prompt
            payload = {
                "race_id": race_id,
                "state": state,
                "office": office,
                "year": year,
                "district": district,
                "candidates": [{"name": c.name, "party": c.party, "incumbent": bool(c.incumbent)} for c in candidates],
            }
            prompt = (
                "You are cleaning a list of candidate-like strings. "
                "Return a JSON array with unique candidates for this race only, each object = {name, party?, incumbent?}. "
                "Drop organizations or generic terms. Normalize party to Democratic/Republican/Independent/Libertarian/Green/Nonpartisan/Unaffiliated if present."
            )
            result_text = await self.providers.run(TaskType.LLM_JSON, system=None, user=prompt, data=payload)
            cleaned = json.loads(result_text)
            out: List[DiscoveredCandidate] = []
            for it in cleaned:
                name = str(it.get("name", "")).strip()
                if not self._looks_like_person(name):
                    continue
                party = self._normalize_party(it.get("party"))
                incumbent = bool(it.get("incumbent", False))
                out.append(DiscoveredCandidate(name=name, party=party, incumbent=incumbent, sources=[]))
            # Merge with original to keep sources
            merged = self._merge_and_dedupe(out + candidates)
            return merged
        except Exception as e:
            _jlog(logging.WARNING, "ai_refine.error", trace_id, **_exc_fields(e))
            return self._merge_and_dedupe(candidates)

    # ---------------------- merge/dedupe & scoring ---------------------- #

    def _merge_and_dedupe(self, items: List[DiscoveredCandidate]) -> List[DiscoveredCandidate]:
        by_name: Dict[str, DiscoveredCandidate] = {}
        for c in items:
            key = self._name_key(c.name)
            if not key:
                continue
            existing = by_name.get(key)
            if not existing:
                # ensure sources list exists & stringified
                srcs = [self._norm_url(s) for s in getattr(c, "sources", []) if s]
                by_name[key] = DiscoveredCandidate(
                    name=c.name.strip(),
                    party=self._pick_party(c.party),
                    incumbent=bool(c.incumbent),
                    sources=list(dict.fromkeys(srcs))[:8],
                )
                continue
            # Merge party/incumbent
            if not existing.party and c.party:
                existing.party = self._pick_party(c.party)
            if c.incumbent:
                existing.incumbent = True
            # Merge sources
            for s in getattr(c, "sources", []) or []:
                s_norm = self._norm_url(s)
                if s_norm and s_norm not in existing.sources:
                    existing.sources.append(s_norm)
            if len(existing.sources) > 8:
                existing.sources = existing.sources[:8]
        # Cap final list to something reasonable
        return list(by_name.values())[:12]

    def _confidence(self, candidates: List[DiscoveredCandidate], has_primary_date: bool, trace_id: str) -> ConfidenceLevel:
        if not candidates:
            lvl = ConfidenceLevel.LOW
        elif any(self._source_is_gov(s) for c in candidates for s in getattr(c, "sources", []) or []):
            lvl = ConfidenceLevel.HIGH
        elif has_primary_date and len(candidates) >= 2:
            lvl = ConfidenceLevel.MEDIUM
        else:
            lvl = ConfidenceLevel.MEDIUM
        _jlog(
            logging.INFO,
            "confidence.result",
            trace_id,
            candidates=len(candidates),
            has_gov=any(self._source_is_gov(s) for c in candidates for s in getattr(c, "sources", []) or []),
            primary_date=has_primary_date,
            confidence=str(lvl.value),
        )
        return lvl

    def _incumbent_party(self, candidates: List[DiscoveredCandidate]) -> Optional[str]:
        for c in candidates:
            if getattr(c, "incumbent", False) and c.party:
                return c.party
        return None

    def _sanitize_candidates_for_json(self, candidates: List[DiscoveredCandidate]) -> List[DiscoveredCandidate]:
        out: List[DiscoveredCandidate] = []
        for c in candidates:
            # Convert any non-primitive URLs to plain strings
            srcs = []
            for s in getattr(c, "sources", []) or []:
                try:
                    srcs.append(self._norm_url(s))
                except Exception:
                    continue
            out.append(DiscoveredCandidate(name=c.name.strip(), party=c.party, incumbent=bool(c.incumbent), sources=srcs))
        return out

    # ---------------------- small NLP-ish helpers ---------------------- #

    def _regex_scan_names(self, text: str) -> List[str]:
        pats = [
            r"\b([A-Z][a-z]+(?:\s+[A-Z]\.)?\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?)\b",  # First Last / First M. Last
            r"\b(?:Senator|Rep\.|Representative|Gov\.|Governor|Mayor|Judge)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b",
        ]
        out: List[str] = []
        seen: set[str] = set()
        for p in pats:
            for m in re.finditer(p, text):
                name = m.group(1).strip()
                key = self._name_key(name)
                if key and key not in seen and self._looks_like_person(name):
                    out.append(name)
                    seen.add(key)
        return out

    def _looks_like_person(self, name: str) -> bool:
        if not name:
            return False
        n = re.sub(r"\s+", " ", name.strip())
        low = n.lower()
        if low in NAME_STOP_WORDS:
            return False
        # Must be 2–4 tokens; tokens must start with capital letters (allow hyphen)
        tokens = [t for t in re.split(r"[\s\u00A0]+", n) if t]
        if len(tokens) < 2 or len(tokens) > 4:
            return False
        if any(t[0].islower() for t in tokens if t and t[0].isalpha()):
            return False
        # Avoid common org/office words
        if any(w in low for w in ["party", "senate", "house", "state", "united", "district"]):
            return False
        return True

    def _party_from_context(self, text: str, name: str) -> Optional[str]:
        # Look around the name for (D)/(R)/words
        try:
            window = 140
            idx = text.find(name)
            if idx == -1:
                idx = text.lower().find(name.lower())
            if idx == -1:
                return None
            start = max(0, idx - window)
            end = min(len(text), idx + len(name) + window)
            blob = text[start:end]
            # Parenthetical code
            m = re.search(r"\((D|R|I|L|G)\)", blob)
            if m:
                return PARTY_ALIASES.get(m.group(1).lower())
            # Word variants
            for k, v in PARTY_ALIASES.items():
                if re.search(rf"\b{k}\b", blob, re.IGNORECASE):
                    return v
        except Exception:
            return None
        return None

    def _is_incumbent(self, text: str, name: str) -> bool:
        try:
            window = 120
            idx = text.find(name)
            if idx == -1:
                idx = text.lower().find(name.lower())
            if idx == -1:
                return False
            start = max(0, idx - window)
            end = min(len(text), idx + len(name) + window)
            blob = text[start:end].lower()
            return any(
                k in blob for k in ["incumbent", "seeking re-election", "seeking reelection", "running for re-election"]
            )  # noqa: E501
        except Exception:
            return False

    # ---------------------- parsing & misc ---------------------- #

    def _parse_race_id(self, race_id: str, trace_id: str) -> Tuple[str, str, int, Optional[str], Optional[str]]:
        m = SLUG_PATTERN.match(race_id.lower())
        if not m:
            _jlog(logging.ERROR, "race_id.parse.invalid", trace_id, race_id=race_id)
            raise ValueError(f"Invalid race_id format: {race_id}")
        state = m.group("state").upper()
        office = m.group("office")
        year = int(m.group("year"))
        district = m.group("district")
        if district:
            district = "AL" if district.lower() == "al" else district.zfill(2) if district.isdigit() else district
        kind = m.group("kind")

        # sanity checks
        if state not in STATE_NAME:
            _jlog(logging.ERROR, "race_id.parse.bad_state", trace_id, state=state)
            raise ValueError(f"Invalid state code: {state}")
        cur = datetime.utcnow().year
        if not (cur - 2 <= year <= cur + 2):
            _jlog(logging.ERROR, "race_id.parse.bad_year", trace_id, year=year)
            raise ValueError("Year out of reasonable range")

        _jlog(
            logging.INFO,
            "race_id.parse.success",
            trace_id,
            race_id=race_id,
            state=state,
            office_type=office,
            year=year,
            district=district,
            kind=kind,
        )
        return state, office, year, district, kind

    def _get_office_info(self, office: str) -> Dict[str, Any]:
        info = self.office_mappings.get(office)
        if info:
            return info
        # Generic fallback
        return {
            "full_name": office.replace("-", " ").title(),
            "race_type": "unknown",
            "term_years": 4,
            "major_issues": ["Economy", "Healthcare", "Education"],
        }

    def _calculate_election_date(self, year: int) -> datetime:
        # US general: first Tuesday after first Monday in November
        nov1 = datetime(year, 11, 1)
        days_to_monday = (7 - nov1.weekday()) % 7
        first_monday = nov1 + timedelta(days=days_to_monday)
        return first_monday + timedelta(days=1)

    def _get_primary_date(self, state: str, year: int) -> Optional[datetime]:
        date_str = PRIMARY_DATE_BY_STATE.get(year, {}).get(state)
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            return None

    def _build_jurisdiction(self, state: str, district: Optional[str]) -> str:
        if district:
            return f"{state}-AL" if district == "AL" else f"{state}-{district}"
        return state

    def _get_major_issues(self, office: str) -> List[str]:
        return self.office_mappings.get(office, {}).get("major_issues", ["Economy", "Healthcare", "Education"])

    def _geo_keywords(self, state: str, district: Optional[str]) -> List[str]:
        out = [state]
        if state in STATE_NAME:
            out.append(STATE_NAME[state])
        if district:
            if district == "AL":
                out += ["At-Large", "CD-AL", f"{state}-AL", "at-large"]
            else:
                out += [f"District {district}", f"CD-{district}", f"{state}-{district}"]
        return out

    # ---------------------- small URL helpers ---------------------- #

    def _is_trusted(self, url: str) -> bool:
        try:
            host = urlparse(url).netloc.replace("www.", "").lower()
            return any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS)
        except Exception:
            return False

    def _norm_url(self, url: Any) -> str:
        if not url:
            return ""
        if not isinstance(url, str):
            url = str(url)
        try:
            p = urlparse(url)
            netloc = p.netloc.lower().replace("www.", "")
            path = re.sub(r"/(amp|mobile|print)/?", "/", p.path or "")
            query = [
                (k, v)
                for k, v in parse_qsl(p.query, keep_blank_values=True)
                if not k.lower().startswith(("utm_", "gclid", "fbclid"))
            ]
            return urlunparse((p.scheme or "https", netloc, path.rstrip("/"), "", urlencode(query), ""))
        except Exception:
            return url

    def _source_is_gov(self, url: str) -> bool:
        try:
            host = urlparse(url).netloc.lower()
            return host.endswith(".gov") or "fec.gov" in host
        except Exception:
            return False

    def _name_key(self, name: str) -> str:
        if not name:
            return ""
        n = re.sub(r"\s+", " ", name.strip().lower())
        n = re.sub(r"[^a-z\s-]", "", n)
        return n

    def _pick_party(self, raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        return self._normalize_party(raw)

    def _normalize_party(self, raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        low = str(raw).strip().lower()
        return PARTY_ALIASES.get(low, raw if low and low[0].isalpha() else None)
