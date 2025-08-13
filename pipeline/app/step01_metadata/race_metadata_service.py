"""
Race Metadata Extraction Service (LLM-first, minimal sources)

Design goals
------------
- Minimal seeds (Wikipedia + Ballotpedia + FEC when federal).
- Prefer a single LLM (OpenAI gpt-4o-mini) for structured extraction.
- If the initial pass yields no candidates, do ONE web search and retry
  with the top 3 trusted results.
- Providers are used via ProviderRegistry.generate_json(TaskType.EXTRACT, ...),
  with an explicit provider/model override (and graceful fallback).
- JSON-safe sources (plain strings), tight noise filtering, and small, readable code.

This module is intended to replace the older heuristic-heavy service.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlparse

from shared.state_constants import PRIMARY_DATE_BY_STATE, STATE_NAME

from ..providers.base import ProviderRegistry, TaskType
from ..schema import Candidate, ConfidenceLevel, FreshSearchQuery, RaceJSON, RaceMetadata, Source, SourceType
from ..step03_fetch import WebContentFetcher
from ..step04_extract import ContentExtractor
from ..utils.search_utils import SearchUtils

logger = logging.getLogger(__name__)

SLUG_PATTERN = re.compile(
    r"^(?P<state>[a-z]{2})-(?P<office>[a-z]+(?:-[a-z]+)*?)"
    r"(?:-(?P<district>\d{1,2}|al))?-(?P<year>\d{4})"
    r"(?:-(?P<kind>primary|runoff|special))?$",
)

TRUSTED_HOSTS = ("wikipedia.org", "ballotpedia.org", "fec.gov")


# --------------------------- logging helpers --------------------------- #


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def _jlog(level: int, event: str, trace_id: str, **fields: Any) -> None:
    payload = {
        "ts": _now_iso(),
        "level": logging.getLevelName(level).lower(),
        "event": event,
        "trace_id": trace_id,
        "component": "RaceMetadataServiceLLM",
        **fields,
    }
    try:
        logger.log(level, json.dumps(payload, default=str))
    except Exception:
        logger.log(level, f"{event} | {fields}")


# ------------------------------ service ------------------------------- #


class RaceMetadataService:
    """
    LLM-first race metadata extractor:
    1) Build 2–3 canonical seed URLs for the race.
    2) Fetch & extract text.
    3) Ask a single model (gpt-4o-mini) for strict JSON {candidates[], incumbent_party?}.
    4) If empty → do one search → take top 3 trusted results → refetch → retry LLM.
    """

    def __init__(self, providers: Optional[ProviderRegistry] = None) -> None:
        self.providers = providers
        self.fetcher = WebContentFetcher()
        self.extractor = ContentExtractor()
        self.search = SearchUtils({"max_results_per_query": 8, "per_host_concurrency": 4})

        self.office_info = {
            "senate": {
                "full": "U.S. Senate",
                "type": "federal",
                "term_years": 6,
                "issues": ["Healthcare", "Economy", "Foreign Policy", "Climate/Energy"],
            },
            "house": {
                "full": "U.S. House of Representatives",
                "type": "federal",
                "term_years": 2,
                "issues": ["Healthcare", "Economy", "Education", "Immigration"],
            },
            "governor": {
                "full": "Governor",
                "type": "state",
                "term_years": 4,
                "issues": ["Economy", "Education", "Healthcare", "Climate/Energy"],
            },
        }

    # ------------------------------ API ------------------------------ #

    async def extract_race_metadata(self, race_id: str) -> RaceJSON:
        trace_id = uuid.uuid4().hex
        t0 = time.perf_counter()
        _jlog(logging.INFO, "race_metadata.extract.start", trace_id, race_id=race_id)

        try:
            state, office, year, district, kind = self._parse_race_id(race_id, trace_id)
            is_primary = kind == "primary"
            info = self.office_info.get(
                office,
                {
                    "full": office.replace("-", " ").title(),
                    "type": "unknown",
                    "term_years": 4,
                    "issues": ["Economy", "Healthcare", "Education"],
                },
            )
            election_date = self._general_election_date(year)
            primary_date = self._primary_date(state, year) if is_primary else None

            # ----- Phase 1: minimal seeds (wiki + ballotpedia + fec if federal) -----
            seeds = self._seed_urls(state, office, year, district)
            _jlog(logging.INFO, "seeds.built", trace_id, count=len(seeds), urls=seeds)

            docs = await self._fetch_and_extract_docs(seeds, trace_id)

            # ----- LLM pass (preferred model: openai:gpt-4o-mini) -----
            candidates, incumbent_party, source_list = await self._llm_candidates(
                state=state,
                office=office,
                year=year,
                district=district,
                is_primary=is_primary,
                info=info,
                docs=docs,
                trace_id=trace_id,
            )

            # ----- Phase 2: one-shot search fallback if empty -----
            if not candidates:
                _jlog(logging.INFO, "fallback_search.start", trace_id)
                more_urls = await self._one_search(state, office, year, district, trace_id)
                _jlog(logging.INFO, "fallback_search.urls", trace_id, urls=more_urls)
                if more_urls:
                    more_docs = await self._fetch_and_extract_docs(more_urls, trace_id)
                    candidates, incumbent_party, source_list = await self._llm_candidates(
                        state=state,
                        office=office,
                        year=year,
                        district=district,
                        is_primary=is_primary,
                        info=info,
                        docs=more_docs,
                        trace_id=trace_id,
                    )

            # ----- Assemble result or fallback -----
            if not candidates:
                _jlog(logging.WARNING, "llm.yielded_zero", trace_id)
                return self._empty_meta(race_id, state, office, year, info, election_date, is_primary, primary_date)

            confidence = self._confidence(candidates, source_list)
            meta = RaceMetadata(
                race_id=race_id,
                state=state,
                office_type=office,
                year=year,
                full_office_name=info["full"],
                jurisdiction=self._jurisdiction(state, district),
                district=district,
                election_date=election_date,
                race_type=info["type"],
                is_primary=is_primary,
                primary_date=primary_date,
                is_special_election=(kind == "special"),
                is_runoff=(kind == "runoff"),
                incumbent_party=incumbent_party or self._incumbent_party(candidates),
                major_issues=[],
                geographic_keywords=self._geo_keywords(state, district),
                confidence=confidence,
                extracted_at=datetime.utcnow(),
            )

            race_json = RaceJSON(
                id=race_id,
                election_date=election_date,
                candidates=candidates,
                updated_utc=datetime.utcnow(),
                generator=[],
                race_metadata=meta,
            )

            _jlog(
                logging.INFO,
                "race_metadata.extract.success",
                trace_id,
                race_id=race_id,
                candidates=len(candidates),
                confidence=str(confidence.value),
                total_duration_ms=int((time.perf_counter() - t0) * 1000),
            )
            return race_json

        except Exception as e:
            _jlog(logging.ERROR, "race_metadata.extract.error", trace_id, error=str(e))
            # conservative fallback (JSON-safe)
            return self._empty_meta(
                race_id=race_id,
                state=race_id.split("-")[0].upper() if "-" in race_id else "",
                office=race_id.split("-")[1] if "-" in race_id else "",
                year=int(race_id.split("-")[-1]) if race_id.split("-")[-1].isdigit() else datetime.utcnow().year,
                info=self.office_info.get("senate", {"full": "U.S. Senate", "type": "federal", "issues": ["Economy"]}),
                election_date=self._general_election_date(datetime.utcnow().year),
                is_primary=False,
                primary_date=None,
            )

    # --------------------------- internals ---------------------------- #

    def _parse_race_id(self, race_id: str, trace_id: str) -> Tuple[str, str, int, Optional[str], Optional[str]]:
        m = SLUG_PATTERN.match(race_id.lower())
        if not m:
            raise ValueError(f"Invalid race_id format: {race_id}")
        state = m.group("state").upper()
        office = m.group("office")
        year = int(m.group("year"))
        district = m.group("district")
        if district:
            district = "AL" if district.lower() == "al" else district.zfill(2) if district.isdigit() else district
        kind = m.group("kind")
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

    def _seed_urls(self, state: str, office: str, year: int, district: Optional[str]) -> List[str]:
        """
        Canonical seeds (2–3):
          - Wikipedia
          - Ballotpedia (NOTE: year at the end)
          - FEC list for federal races
        """
        state_name = STATE_NAME.get(state, state).replace(" ", "_")
        seeds: List[str] = []

        if office == "senate":
            wiki = f"https://en.wikipedia.org/wiki/{year}_United_States_Senate_election_in_{state_name}"
            bp = f"https://ballotpedia.org/United_States_Senate_election_in_{state_name},_{year}"
            fec = self._fec_url("senate", state, year)
            seeds.extend([wiki, bp, fec])
        elif office == "house":
            wiki = f"https://en.wikipedia.org/wiki/{year}_United_States_House_of_Representatives_elections_in_{state_name}"
            bp = f"https://ballotpedia.org/United_States_House_of_Representatives_elections_in_{state_name},_{year}"
            fec = self._fec_url("house", state, year, district)
            seeds.extend([wiki, bp, fec])
        else:
            # non-federal minimal attempt
            seeds.append(f"https://ballotpedia.org/{STATE_NAME.get(state, state).replace(' ', '_')}_elections,_" f"{year}")

        # keep only trusted & unique
        out: List[str] = []
        seen = set()
        for u in seeds:
            if not u:
                continue
            host = urlparse(u).netloc.lower()
            if not any(h in host for h in TRUSTED_HOSTS):
                continue
            if u not in seen:
                out.append(u)
                seen.add(u)
        return out[:3]

    async def _fetch_and_extract_docs(self, urls: List[str], trace_id: str) -> List[Dict[str, str]]:
        # Fetch
        _jlog(logging.INFO, "sources.fetch.start", trace_id, count=len(urls))
        fetched = await self.fetcher.fetch_content([self._mk_source(u) for u in urls if u])
        ok = sum(1 for f in fetched if getattr(f, "ok", True))
        _jlog(logging.INFO, "sources.fetch.done", trace_id, ok=ok, total=len(fetched))

        # Extract
        extracted = await self.extractor.extract_content(fetched)
        docs: List[Dict[str, str]] = []
        for e in extracted:
            url = ""
            try:
                src = getattr(e, "source", None)
                url = str(getattr(src, "url", "")) if src else ""
            except Exception:
                url = ""
            text = (getattr(e, "text", "") or "").strip()
            if url and text:
                docs.append({"url": url, "text": text[:8000]})  # cap to keep token usage sane
        _jlog(logging.INFO, "sources.extracted", trace_id, count=len(docs))
        return docs

    async def _llm_candidates(
        self,
        *,
        state: str,
        office: str,
        year: int,
        district: Optional[str],
        is_primary: bool,
        info: Dict[str, Any],
        docs: List[Dict[str, str]],
        trace_id: str,
    ) -> Tuple[List[Candidate], Optional[str], List[str]]:
        if not docs:
            return [], None, []

        if not self.providers:
            _jlog(logging.WARNING, "providers.none", trace_id)
            return [], None, []

        # Build prompt for strict-JSON extraction
        state_name = STATE_NAME.get(state, state)
        header = (
            f"Race: {year} {state_name} {info['full']}"
            + (f" (district {int(district)})" if district and district.isdigit() else "")
            + (", primary" if is_primary else "")
            + "."
        )

        # Keep only trusted sources in the corpus we pass
        trusted_docs = [d for d in docs if any(h in urlparse(d["url"]).netloc for h in TRUSTED_HOSTS)]
        if not trusted_docs:
            trusted_docs = docs[:3]
        trusted_docs = trusted_docs[:3]

        corpus_lines = ["Sources:"]
        for d in trusted_docs:
            corpus_lines.append(f"- {d['url']}")
        corpus_lines.append("\nExcerpts:")
        for d in trusted_docs:
            corpus_lines.append(f"\nSOURCE: {d['url']}\n{d['text']}")

        schema_hint = (
            "Return ONLY JSON (no prose) matching:\n"
            "{\n"
            '  "candidates": [\n'
            '    {"name": "string", "party": "Democratic|Republican|Independent|Libertarian|Green|Nonpartisan|Unaffiliated|null", "incumbent": true|false|null}\n'
            "  ],\n"
            '  "incumbent_party": "Democratic|Republican|Independent|Libertarian|Green|Nonpartisan|Unaffiliated|null"\n'
            "}\n"
        )

        prompt = (
            "You are a precise elections data normalizer.\n"
            f"{header}\n\n"
            "Task:\n"
            "- Extract ONLY real candidate names for THIS race.\n"
            "- Ignore committees, counties, offices, headings, page furniture, and phrases like 'Candidate Connection' or 'Key Messages'.\n"
            "- If a party is unclear, use null.\n"
            "- Mark incumbent=true only if explicitly stated for THIS office.\n\n"
            f"{schema_hint}"
            "Do not include any explanation—only the JSON.\n\n" + "\n".join(corpus_lines)
        )

        # Ask the provider for JSON using a specific model (gpt-4o-mini).
        # If that exact model is unavailable, gracefully fall back to registry defaults.
        try:
            schema = {
                "type": "json_schema",
                "json_schema": {
                    "name": "race_metadata",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "candidates": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "name": {"type": "string"},
                                        "party": {
                                            "type": ["string", "null"],
                                            "enum": [
                                                "Democratic",
                                                "Republican",
                                                "Independent",
                                                "Libertarian",
                                                "Green",
                                                "Nonpartisan",
                                                "Unaffiliated",
                                                None,  # will serialize to JSON null
                                            ],
                                        },
                                        "incumbent": {"type": ["boolean", "null"]},
                                    },
                                    # strict schemas require listing all keys here
                                    "required": ["name", "party", "incumbent"],
                                },
                            },
                            "incumbent_party": {
                                "type": ["string", "null"],
                                "enum": [
                                    "Democratic",
                                    "Republican",
                                    "Independent",
                                    "Libertarian",
                                    "Green",
                                    "Nonpartisan",
                                    "Unaffiliated",
                                    None,
                                ],
                            },
                        },
                        "required": ["candidates", "incumbent_party"],
                    },
                },
            }

            result = await self.providers.generate_json(
                TaskType.EXTRACT,
                prompt,
                provider_name="openai",
                model_id="gpt-4o-mini",
                response_format=schema,
                max_tokens=1200,
            )
        except Exception as e:
            _jlog(logging.WARNING, "llm.preferred_failed", trace_id, error=str(e))
            try:
                result = await self.providers.generate_json(
                    TaskType.EXTRACT,
                    prompt,
                    response_format=schema,
                    max_tokens=1200,
                )
            except Exception as e2:
                _jlog(logging.WARNING, "llm.fallback_failed", trace_id, error=str(e2))
                return [], None

        raw_cands: List[Dict[str, Any]] = (result or {}).get("candidates") or []
        inc_party = (result or {}).get("incumbent_party")

        # Sanitize and cap
        out: List[Candidate] = []
        seen = set()
        source_list = [d["url"] for d in trusted_docs]
        for it in raw_cands:
            name = (it.get("name") or "").strip()
            if not name or self._looks_like_noise(name):
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)

            party = self._norm_party(it.get("party"))
            inc = it.get("incumbent")
            inc = bool(inc) if inc is not None else False

            out.append(Candidate(name=name, party=party, incumbent=inc))
            if len(out) >= 12:
                break

        return out, self._norm_party(inc_party) if inc_party else None, source_list

    async def _one_search(
        self,
        state: str,
        office: str,
        year: int,
        district: Optional[str],
        trace_id: str,
    ) -> List[str]:
        """
        Do a single broad query and return up to 3 trusted URLs.
        """
        state_name = STATE_NAME.get(state, state)
        district_text = ""
        if district:
            district_text = (
                " at-large" if district == "AL" else f" district {int(district) if district.isdigit() else district}"
            )
        q = FreshSearchQuery(
            race_id=f"{state.lower()}-{office}-{year}",
            text=f"{year} {state_name}{district_text} {office} election candidates",
            max_results=10,
            date_restrict="y2",
        )
        try:
            results: List[Source] = await self.search.search_general(q)
        except Exception as e:
            _jlog(logging.WARNING, "fallback_search.error", trace_id, error=str(e))
            return []

        # Filter trusted & unique
        trusted: List[str] = []
        seen = set()
        for r in results or []:
            url = str(getattr(r, "url", "")).strip()
            if not url:
                continue
            host = urlparse(url).netloc.lower().replace("www.", "")
            if not any(host.endswith(h) or host == h for h in TRUSTED_HOSTS):
                continue
            if url not in seen:
                trusted.append(url)
                seen.add(url)
            if len(trusted) >= 3:
                break
        return trusted

    # --------------------------- helpers ---------------------------- #

    def _looks_like_noise(self, name: str) -> bool:
        low = name.lower().strip()
        # obvious junk
        junk = (
            "candidate connection",
            "republican party",
            "democratic party",
            "key messages",
            "state senate",
            "state house",
            "house of representatives",
            "county",
            "city",
            "ballotpedia",
        )
        if any(t in low for t in junk):
            return True

        # require 2–4 tokens, majority capitalized initials
        tokens = [t for t in re.split(r"\s+", name.strip()) if t]
        if len(tokens) < 2 or len(tokens) > 4:
            return True
        caps = sum(1 for t in tokens if t and t[0].isupper())
        if caps < 2:
            return True
        return False

    def _norm_party(self, party: Optional[str]) -> Optional[str]:
        if not party:
            return None
        p = str(party).strip().lower()
        aliases = {
            "d": "Democratic",
            "dem": "Democratic",
            "democrat": "Democratic",
            "democratic": "Democratic",
            "r": "Republican",
            "rep": "Republican",
            "republican": "Republican",
            "i": "Independent",
            "ind": "Independent",
            "independent": "Independent",
            "l": "Libertarian",
            "libertarian": "Libertarian",
            "g": "Green",
            "green": "Green",
            "np": "Nonpartisan",
            "npp": "Nonpartisan",
            "nonpartisan": "Nonpartisan",
            "u": "Unaffiliated",
            "unaffiliated": "Unaffiliated",
        }
        return aliases.get(p, party if p and p[0].isalpha() else None)

    def _url_host(self, u) -> str:
        try:
            host = getattr(u, "host", None)
            if host:
                return host.lower().replace("www.", "")
        except Exception:
            pass
        try:
            return urlparse(str(u)).netloc.lower().replace("www.", "")
        except Exception:
            return ""

    def _confidence(self, candidates: List[Candidate], sources: List[str]) -> ConfidenceLevel:
        def is_fec(u: str) -> bool:
            return self._url_host(u).endswith("fec.gov")

        has_fec = any(is_fec(s) for s in sources)
        if has_fec and len(candidates) >= 2:
            return ConfidenceLevel.HIGH
        return ConfidenceLevel.MEDIUM if candidates else ConfidenceLevel.LOW

    def _incumbent_party(self, candidates: List[Candidate]) -> Optional[str]:
        for c in candidates:
            if getattr(c, "incumbent", False) and c.party:
                return c.party
        return None

    def _jurisdiction(self, state: str, district: Optional[str]) -> str:
        if district:
            return f"{state}-AL" if district == "AL" else f"{state}-{district}"
        return state

    def _geo_keywords(self, state: str, district: Optional[str]) -> List[str]:
        out = [state]
        if state in STATE_NAME:
            out.append(STATE_NAME[state])
        if district:
            out.append("At-Large" if district == "AL" else f"District {district}")
        return out

    def _general_election_date(self, year: int) -> datetime:
        # First Tuesday after the first Monday in November
        nov1 = datetime(year, 11, 1)
        days_to_monday = (7 - nov1.weekday()) % 7
        first_monday = nov1 + timedelta(days=days_to_monday)
        return first_monday + timedelta(days=1)

    def _primary_date(self, state: str, year: int) -> Optional[datetime]:
        s = (PRIMARY_DATE_BY_STATE.get(year, {}) or {}).get(state)
        try:
            return datetime.strptime(s, "%Y-%m-%d") if s else None
        except Exception:
            return None

    def _mk_source(self, url: str) -> Source:
        # Build a minimally valid Source to satisfy schema validation
        return Source(
            url=url,
            type=SourceType.WEBSITE if hasattr(SourceType, "WEBSITE") else next(iter(SourceType)),
            title=None,
            description=None,
            last_accessed=datetime.utcnow(),
            published_at=None,
            score=0.0,
            scoring_reason="seed",
            is_fresh=False,
        )

    def _empty_meta(
        self,
        race_id: str,
        state: str,
        office: str,
        year: int,
        info: Dict[str, Any],
        election_date: datetime,
        is_primary: bool,
        primary_date: Optional[datetime],
    ) -> RaceJSON:
        meta = RaceMetadata(
            race_id=race_id,
            state=state,
            office_type=office,
            year=year,
            full_office_name=info.get("full", office.title()),
            jurisdiction=state,
            district=None,
            election_date=election_date,
            race_type=info.get("type", "unknown"),
            is_primary=is_primary,
            primary_date=primary_date,
            is_special_election=False,
            is_runoff=False,
            incumbent_party=None,
            major_issues=[],
            geographic_keywords=[state, STATE_NAME.get(state, state)],
            confidence=ConfidenceLevel.LOW,
            extracted_at=datetime.utcnow(),
        )

        return RaceJSON(
            id=race_id,
            election_date=election_date,
            candidates=[],
            updated_utc=datetime.utcnow(),
            generator=[],
            race_metadata=meta,
        )

    # --------------------------- FEC helper ---------------------------- #

    def _fec_url(self, office: str, state: str, year: int, district: Optional[str] = None) -> str:
        base = "https://www.fec.gov/data/candidates"
        if office == "senate":
            path = "senate/"
            q = {"election_year": year, "state": state}
        else:
            path = "house/"
            q = {"election_year": year, "state": state}
            if district and district.isdigit():
                q["district"] = int(district)
        return f"{base}/{path}?{urlencode(q)}"
