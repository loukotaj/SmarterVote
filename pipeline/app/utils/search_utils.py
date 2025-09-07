"""
Search utilities for source discovery in SmarterVote Pipeline.

Backwards-compatibility notes
- Public methods kept: search_google_custom, search_general,
  generate_issue_query, generate_candidate_issue_queries, deduplicate_sources.
- Added helpers are additive and safe for other services to ignore.
"""

import asyncio
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..schema import CanonicalIssue, FreshSearchQuery, RaceMetadata, Source, SourceType

logger = logging.getLogger(__name__)


class SearchUtils:
    """Utilities for performing searches to discover sources."""

    _STATE_MAP: Dict[str, str] = {
        "AL": "Alabama",
        "AK": "Alaska",
        "AZ": "Arizona",
        "AR": "Arkansas",
        "CA": "California",
        "CO": "Colorado",
        "CT": "Connecticut",
        "DE": "Delaware",
        "FL": "Florida",
        "GA": "Georgia",
        "HI": "Hawaii",
        "ID": "Idaho",
        "IL": "Illinois",
        "IN": "Indiana",
        "IA": "Iowa",
        "KS": "Kansas",
        "KY": "Kentucky",
        "LA": "Louisiana",
        "ME": "Maine",
        "MD": "Maryland",
        "MA": "Massachusetts",
        "MI": "Michigan",
        "MN": "Minnesota",
        "MS": "Mississippi",
        "MO": "Missouri",
        "MT": "Montana",
        "NE": "Nebraska",
        "NV": "Nevada",
        "NH": "New Hampshire",
        "NJ": "New Jersey",
        "NM": "New Mexico",
        "NY": "New York",
        "NC": "North Carolina",
        "ND": "North Dakota",
        "OH": "Ohio",
        "OK": "Oklahoma",
        "OR": "Oregon",
        "PA": "Pennsylvania",
        "RI": "Rhode Island",
        "SC": "South Carolina",
        "SD": "South Dakota",
        "TN": "Tennessee",
        "TX": "Texas",
        "UT": "Utah",
        "VT": "Vermont",
        "VA": "Virginia",
        "WA": "Washington",
        "WV": "West Virginia",
        "WI": "Wisconsin",
        "WY": "Wyoming",
        "DC": "District of Columbia",
        "PR": "Puerto Rico",
    }

    _REDIRECTOR_HOSTS: Set[str] = {
        "t.co",
        "l.facebook.com",
        "lm.facebook.com",
        "outlook.office.com",
        "link.agenda4democracy.org",
        "lnkd.in",
        "bit.ly",
        "tinyurl.com",
        "mail.google.com",
        "news.google.com",
    }

    _TRACKING_PARAMS: Set[str] = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
        "mc_cid",
        "mc_eid",
        "pk_campaign",
        "pk_kwd",
        "irgwc",
        "icid",
        "ref",
        "ref_src",
        "cmpid",
    }

    def __init__(self, search_config: dict):
        self.search_config = search_config
        self.cache: Dict[str, Tuple[datetime, List[Source]]] = {}
        self.cache_ttl = search_config.get("cache_ttl_seconds", 300)
        self.per_host_concurrency = search_config.get("per_host_concurrency", 5)
        self._host_semaphores: Dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(self.per_host_concurrency))
        # Choose which external search provider to use. Defaults to Serper, with Google CSE as a fallback option.
        self.search_provider = search_config.get("search_provider", "serper").lower()

        self.issue_synonyms: Dict[CanonicalIssue, List[str]] = {
            CanonicalIssue.HEALTHCARE: ["health care", "medical", "medicare", "medicaid"],
            CanonicalIssue.ECONOMY: ["economic", "jobs", "employment", "taxes", "budget"],
            CanonicalIssue.CLIMATE_ENERGY: ["climate change", "environment", "renewable energy", "fossil fuels"],
            CanonicalIssue.REPRODUCTIVE_RIGHTS: ["abortion", "reproductive health", "family planning"],
            CanonicalIssue.IMMIGRATION: ["border", "refugees", "citizenship", "visa"],
            CanonicalIssue.GUNS_SAFETY: ["gun control", "firearms", "second amendment", "gun violence"],
            CanonicalIssue.FOREIGN_POLICY: ["international", "defense", "military", "diplomacy"],
            CanonicalIssue.SOCIAL_JUSTICE: [
                "LGBTQ",
                "gay rights",
                "transgender",
                "equality",
                "civil rights",
                "racial justice",
                "gender equality",
                "disability rights",
            ],
            CanonicalIssue.EDUCATION: ["schools", "teachers", "students", "university"],
            CanonicalIssue.TECH_AI: ["technology", "artificial intelligence", "privacy", "internet"],
            CanonicalIssue.ELECTION_REFORM: ["voting rights", "gerrymandering", "campaign finance"],
        }

    # ------------------------- public search APIs ------------------------- #

    async def search_google_custom(self, query: FreshSearchQuery, issue: CanonicalIssue) -> List[Source]:
        """Perform a web search using the configured provider and return raw results."""
        cache_key = f"{query.race_id}:{query.text}:{getattr(query, 'date_restrict', '')}:{getattr(query, 'max_results', '')}"
        now = datetime.utcnow()
        cached = self.cache.get(cache_key)
        if cached and now - cached[0] < timedelta(seconds=self.cache_ttl):
            return cached[1]

        if self.search_provider == "serper":
            results = await self._search_serper(query, issue, now)
        else:
            results = await self._search_google_cse(query, issue, now)

        self.cache[cache_key] = (datetime.utcnow(), results)
        return results

    async def _search_google_cse(self, query: FreshSearchQuery, issue: CanonicalIssue, now: datetime) -> List[Source]:
        """Internal helper for Google Custom Search API."""
        api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

        if not api_key or not search_engine_id:
            logger.warning("Google Custom Search API not configured.")
            return [
                Source(
                    url=f"https://example.com/news/{getattr(issue, 'value', str(issue)).lower()}-{query.race_id}",
                    type=self._choose_type("WEBSITE"),
                    title=f"Fresh: {getattr(issue, 'value', str(issue))} in {query.race_id}",
                    description=f"Fresh search content about {getattr(issue, 'value', str(issue))} for this race",
                    last_accessed=now,
                    published_at=now,
                    is_fresh=True,
                )
            ]

        try:
            import httpx  # type: ignore
        except ImportError:
            logger.warning("httpx not available; returning mock result.")
            return [
                Source(
                    url=f"https://example.com/mock/{getattr(issue, 'value', str(issue)).lower()}-{query.race_id}",
                    type=self._choose_type("WEBSITE"),
                    title=f"Mock: {getattr(issue, 'value', str(issue))} in {query.race_id}",
                    description=f"Mock search content about {getattr(issue, 'value', str(issue))} for this race",
                    last_accessed=now,
                    published_at=now,
                    is_fresh=True,
                )
            ]

        search_url = "https://www.googleapis.com/customsearch/v1"
        date_param = getattr(query, "date_restrict", None)
        num = getattr(query, "max_results", None) or self.search_config.get("top_results_per_query", 5)

        params = {"key": api_key, "cx": search_engine_id, "q": query.text, "num": num}
        if date_param:
            params["dateRestrict"] = date_param

        host = urlparse(search_url).netloc
        async with self._host_semaphores[host]:
            try:
                async with httpx.AsyncClient(timeout=self.search_config.get("http_timeout_seconds", 20)) as client:
                    resp = await client.get(search_url, params=params)
                    resp.raise_for_status()
                    data = resp.json()
            except Exception as e:  # noqa: BLE001
                logger.error("Google Custom Search failed for %s | error=%s", query.text, e)
                return []

        out: List[Source] = []
        for item in data.get("items", []) or []:
            link = item.get("link")
            if not link:
                continue
            link = self._normalize_url(link)
            title = item.get("title", "") or ""
            snippet = item.get("snippet", "") or ""
            published_at = self._extract_published_time(item)
            source_type = self._classify_source(link)
            out.append(
                Source(
                    url=link,
                    type=source_type,
                    title=title,
                    description=snippet,
                    last_accessed=now,
                    published_at=published_at,
                    is_fresh=bool(date_param),
                )
            )

        return self.deduplicate_sources(out)

    async def _search_serper(self, query: FreshSearchQuery, issue: CanonicalIssue, now: datetime) -> List[Source]:
        """Internal helper for Serper search API."""
        api_key = os.getenv("SERPER_API_KEY")
        if not api_key:
            logger.warning("Serper API key not configured.")
            return [
                Source(
                    url=f"https://example.com/serper/{getattr(issue, 'value', str(issue)).lower()}-{query.race_id}",
                    type=self._choose_type("WEBSITE"),
                    title=f"Serper: {getattr(issue, 'value', str(issue))} in {query.race_id}",
                    description=f"Serper search content about {getattr(issue, 'value', str(issue))} for this race",
                    last_accessed=now,
                    published_at=now,
                    is_fresh=True,
                )
            ]

        try:
            import httpx  # type: ignore
        except ImportError:
            logger.warning("httpx not available; returning mock result.")
            return [
                Source(
                    url=f"https://example.com/serper-mock/{getattr(issue, 'value', str(issue)).lower()}-{query.race_id}",
                    type=self._choose_type("WEBSITE"),
                    title=f"Serper mock: {getattr(issue, 'value', str(issue))} in {query.race_id}",
                    description=f"Serper mock search content about {getattr(issue, 'value', str(issue))} for this race",
                    last_accessed=now,
                    published_at=now,
                    is_fresh=True,
                )
            ]

        search_url = "https://google.serper.dev/search"
        date_param = getattr(query, "date_restrict", None)
        num = getattr(query, "max_results", None) or self.search_config.get("top_results_per_query", 5)

        payload: Dict[str, Any] = {"q": query.text, "num": num}
        if date_param:
            payload["tbs"] = f"qdr:{date_param}"

        headers = {"X-API-KEY": api_key}
        host = urlparse(search_url).netloc
        async with self._host_semaphores[host]:
            try:
                async with httpx.AsyncClient(timeout=self.search_config.get("http_timeout_seconds", 20)) as client:
                    resp = await client.post(search_url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
            except Exception as e:  # noqa: BLE001
                logger.error("Serper search failed for %s | error=%s", query.text, e)
                return []

        out: List[Source] = []
        for item in data.get("organic", []) or []:
            link = item.get("link")
            if not link:
                continue
            link = self._normalize_url(link)
            title = item.get("title", "") or ""
            snippet = item.get("snippet", "") or ""
            published_at = None
            date_str = item.get("date")
            if date_str:
                try:
                    published_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except Exception:  # noqa: BLE001
                    published_at = None
            source_type = self._classify_source(link)
            out.append(
                Source(
                    url=link,
                    type=source_type,
                    title=title,
                    description=snippet,
                    last_accessed=now,
                    published_at=published_at,
                    is_fresh=bool(date_param),
                )
            )

        return self.deduplicate_sources(out)

    async def search_general(self, query: FreshSearchQuery) -> List[Source]:
        issue = self._pick_issue("GENERAL")
        return await self.search_google_custom(query, issue)

    # ------------------------- query generation ------------------------- #

    def generate_issue_query(
        self,
        race_id: str,
        issue: CanonicalIssue,
        state: str = None,
        office: str = None,
    ) -> FreshSearchQuery:
        parts = [issue.value]
        if state:
            parts.append(state)
        if office:
            parts.append(office)
        return FreshSearchQuery(
            text=" ".join(parts),
            race_id=race_id,
            issue=issue,
            generated_at=datetime.utcnow(),
        )

    def generate_candidate_issue_queries(
        self,
        race_id: str,
        candidate_name: str,
        issues: List[CanonicalIssue],
        race_metadata: Optional[RaceMetadata],
        limit: int,
    ) -> List[FreshSearchQuery]:
        state = None
        year: Optional[str] = None
        if race_metadata:
            state = race_metadata.state
            year = str(race_metadata.year)
        else:
            parts = (race_id or "").split("-")
            if parts:
                state = parts[0]
            if len(parts) >= 3 and parts[-1].isdigit():
                year = parts[-1]

        queries: List[FreshSearchQuery] = []
        for issue in issues:
            terms = [issue.value] + self.issue_synonyms.get(issue, [])[:2]
            for term in terms:
                base = f'"{candidate_name}" {term}'
                if state:
                    base += f" {state}"
                if year:
                    base += f" {year}"
                queries.append(
                    FreshSearchQuery(
                        text=base,
                        race_id=race_id,
                        issue=issue,
                        generated_at=datetime.utcnow(),
                        max_results=self.search_config.get("top_results_per_query", 5),
                        date_restrict=f"d{self.search_config.get('freshness_days', 30)}",  # keep this one fresh
                    )
                )
                if len(queries) >= limit:
                    return queries
        return queries

    # NEW: super-simple name-only queries to let Google surface the homepage
    def generate_candidate_baseline_queries(
        self,
        race_id: str,
        candidate_name: str,
        race_metadata: Optional[RaceMetadata],
        max_results: int = 5,
    ) -> List[FreshSearchQuery]:
        state = getattr(race_metadata, "state", None) if race_metadata else None
        office = getattr(race_metadata, "office_type", None) if race_metadata else None

        templates = [
            f'"{candidate_name}"',
            f'"{candidate_name}" {state or ""}'.strip(),
            f'"{candidate_name}" {office or ""} {state or ""}'.strip(),
        ]

        out: List[FreshSearchQuery] = []
        for t in templates:
            out.append(
                FreshSearchQuery(
                    text=t,
                    race_id=race_id,
                    issue=self._pick_issue("GENERAL"),
                    generated_at=datetime.utcnow(),
                    max_results=max_results,
                    # no date_restrict — evergreen
                )
            )
        return out

    # NEW: lightly-biased campaign queries (not over-constrained)
    def generate_campaign_homerun_queries(
        self,
        race_id: str,
        candidate_name: str,
        race_metadata: Optional[RaceMetadata],
        max_results: int = 5,
    ) -> List[FreshSearchQuery]:
        state = getattr(race_metadata, "state", None) if race_metadata else None
        office = getattr(race_metadata, "office_type", None) if race_metadata else None

        templates = [
            f'"{candidate_name}" campaign',
            (
                f'"{candidate_name}" "for {office}" {state or ""}'.strip()
                if office
                else f'"{candidate_name}" campaign {state or ""}'.strip()
            ),
            f'"{candidate_name}" site:.org',
            f'"{candidate_name}" site:.com',
        ]

        out: List[FreshSearchQuery] = []
        for t in templates:
            out.append(
                FreshSearchQuery(
                    text=t,
                    race_id=race_id,
                    issue=self._pick_issue("GENERAL"),
                    generated_at=datetime.utcnow(),
                    max_results=max_results,
                )
            )
        return out

    def build_race_seed_queries(
        self,
        race_id: str,
        state: str,
        office: str,
        year: int,
        district: Optional[str],
        trusted_only: bool = True,
    ) -> List[FreshSearchQuery]:
        state_part = state
        district_text = ""
        if district:
            district_text = " at-large" if str(district).upper() == "AL" else f" district {district}"

        if trusted_only:
            targets = [
                f"site:ballotpedia.org {year} {state_part}{district_text} {office} election",
                f"site:wikipedia.org {year} {state_part}{district_text} {office} election",
            ]
            if office in {"senate", "house"}:
                targets.append(f"site:fec.gov {year} {state} {office} candidates")
        else:
            base = f"{year} {state_part}{district_text} {office}"
            targets = [
                f"{base} candidates",
                f"{base} candidate list",
                f"{base} ballotpedia OR wikipedia OR site:.gov",
                f"{base} official campaign website",
            ]

        out: List[FreshSearchQuery] = []
        for t in targets if trusted_only else targets:
            out.append(
                FreshSearchQuery(
                    text=t,
                    race_id=race_id,
                    issue=self._pick_issue("GENERAL"),
                    generated_at=datetime.utcnow(),
                    max_results=10,
                    date_restrict="y2",
                    strict=True,
                )
            )
        return out

    # ------------------------- utilities ------------------------- #

    def deduplicate_sources(self, sources: List[Source]) -> List[Source]:
        """Remove duplicate sources with light URL normalization."""
        seen: Set[str] = set()
        unique: List[Source] = []

        for src in sources:
            norm = self._normalize_url(str(src.url or ""))
            parsed = urlparse(norm)
            # collapse /index.html and trailing slash
            path = parsed.path.replace("/index.html", "/").rstrip("/") or "/"
            key = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
            if key in seen:
                continue
            seen.add(key)
            # write normalized back
            src.url = f"{parsed.scheme}://{parsed.netloc}{path}{('?' + parsed.query) if parsed.query else ''}"
            unique.append(src)

        return unique

    # ------------------------- internal helpers ------------------------- #

    def _extract_published_time(self, item: Dict[str, Any]) -> Optional[datetime]:
        pagemap = item.get("pagemap", {}) or {}
        date_str: Optional[str] = None

        for tag in pagemap.get("metatags", []) or []:
            date_str = (
                tag.get("article:published_time")
                or tag.get("pubdate")
                or tag.get("date")
                or tag.get("dc.date.issued")
                or tag.get("og:updated_time")
            )
            if date_str:
                break

        if not date_str:
            if "newsarticle" in pagemap:
                date_str = (pagemap["newsarticle"][0] or {}).get("datepublished")
            elif "article" in pagemap:
                date_str = (pagemap["article"][0] or {}).get("datepublished")

        if not date_str:
            return None

        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            return None

    def _classify_source(self, url: str) -> SourceType:
        domain = urlparse(url).netloc.lower()
        if domain.endswith(".gov") or "fec.gov" in domain:
            return self._choose_type("GOVERNMENT")
        if "c-span.org" in domain:
            return self._choose_type("WEBSITE")
        if any(s in domain for s in ["twitter.com", "facebook.com", "youtube.com", "tiktok.com", "x.com"]):
            return self._choose_type("SOCIAL_MEDIA")
        if url.lower().endswith(".pdf"):
            return self._choose_type("PDF")
        return self._choose_type("WEBSITE")

    def _choose_type(self, preferred: str) -> SourceType:
        if hasattr(SourceType, preferred):
            return getattr(SourceType, preferred)
        for alt in ("WEBSITE", "WEB", "URL", "ARTICLE", "UNKNOWN"):
            if hasattr(SourceType, alt):
                return getattr(SourceType, alt)
        try:
            return next(iter(SourceType))
        except Exception as e:
            raise AttributeError("SourceType enum has no accessible members") from e

    def _pick_issue(self, preferred: str = "GENERAL") -> CanonicalIssue:
        if hasattr(CanonicalIssue, preferred):
            return getattr(CanonicalIssue, preferred)
        for alt in ("GENERAL_ELECTIONS", "DEFAULT"):
            if hasattr(CanonicalIssue, alt):
                return getattr(CanonicalIssue, alt)
        try:
            return next(iter(CanonicalIssue))
        except Exception as e:
            raise AttributeError("No usable CanonicalIssue enum member found") from e

    # URL normalization: strip trackers, preserve path, avoid redirector noise
    def _normalize_url(self, url: str) -> str:
        if not url:
            return url
        try:
            p = urlparse(url)
            # kill obvious redirector wrappers (keep as-is; true unwrapping requires a fetch)
            host = p.netloc.lower()
            # strip tracking params
            q = [(k, v) for (k, v) in parse_qsl(p.query, keep_blank_values=True) if k not in self._TRACKING_PARAMS]
            cleaned = p._replace(query=urlencode(q, doseq=True))
            return urlunparse(cleaned)
        except Exception:
            return url
