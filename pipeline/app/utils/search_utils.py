"""Search utilities for source discovery in SmarterVote Pipeline.

Backwards-compatibility notes
- Public methods kept: search_google_custom, search_candidate_info, search_general,
  generate_issue_query, generate_candidate_query, generate_candidate_issue_queries,
  deduplicate_sources.
- Added helpers are additive and safe for other services to ignore.
"""

import asyncio
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from ..schema import CanonicalIssue, FreshSearchQuery, RaceMetadata, Source, SourceType

logger = logging.getLogger(__name__)


class SearchUtils:
    """Utilities for performing searches to discover sources."""

    # --- static maps / constants (small, local, no external deps) --- #

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

    def __init__(self, search_config: dict):
        """Initialize with search configuration."""
        self.search_config = search_config
        self.cache: Dict[str, Tuple[datetime, List[Source]]] = {}
        self.cache_ttl = search_config.get("cache_ttl_seconds", 300)
        self.per_host_concurrency = search_config.get("per_host_concurrency", 5)
        self._host_semaphores: Dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(self.per_host_concurrency))

        # Canonical issue synonyms
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
        """Perform Google Custom Search and return raw results."""
        cache_key = f"{query.race_id}:{query.text}"
        now = datetime.utcnow()
        cached = self.cache.get(cache_key)
        if cached and now - cached[0] < timedelta(seconds=self.cache_ttl):
            return cached[1]

        api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

        if not api_key or not search_engine_id:
            logger.warning(
                "Google Custom Search API not configured (missing GOOGLE_SEARCH_API_KEY or GOOGLE_SEARCH_ENGINE_ID)"
            )
            logger.info("Would search Google for: %s", query.text)

            mock_source = Source(
                url=f"https://example.com/news/{(getattr(issue, 'value', str(issue))).lower()}-{query.race_id}",
                type=self._choose_type("WEBSITE"),
                title=f"Fresh: {getattr(issue, 'value', str(issue))} in {query.race_id}",
                description=f"Fresh search content about {getattr(issue, 'value', str(issue))} for this race",
                last_accessed=now,
                published_at=now,
                is_fresh=True,
            )
            self.cache[cache_key] = (now, [mock_source])
            return [mock_source]

        logger.info("Searching Google Custom Search for: %s", query.text)

        try:
            import httpx  # type: ignore
        except ImportError:
            logger.warning("httpx not available for Google search. Using mock results.")
            mock_source = Source(
                url=f"https://example.com/mock/{(getattr(issue, 'value', str(issue))).lower()}-{query.race_id}",
                type=self._choose_type("WEBSITE"),
                title=f"Mock: {getattr(issue, 'value', str(issue))} in {query.race_id}",
                description=f"Mock search content about {getattr(issue, 'value', str(issue))} for this race",
                last_accessed=now,
                published_at=now,
                is_fresh=True,
            )
            self.cache[cache_key] = (now, [mock_source])
            return [mock_source]

        search_url = "https://www.googleapis.com/customsearch/v1"

        date_restrict = getattr(query, "date_restrict", None)
        date_param = date_restrict if date_restrict else f"d{self.search_config.get('freshness_days', 30)}"
        num = getattr(query, "max_results", None) or self.search_config.get("max_results_per_query", 10)

        params = {
            "key": api_key,
            "cx": search_engine_id,
            "q": query.text,
            "num": num,
            "dateRestrict": date_param,
        }

        host = urlparse(search_url).netloc
        async with self._host_semaphores[host]:
            try:
                async with httpx.AsyncClient(timeout=self.search_config.get("http_timeout_seconds", 20)) as client:
                    response = await client.get(search_url, params=params)
                    response.raise_for_status()
                    data = response.json()
            except Exception as e:  # noqa: BLE001
                logger.error("Google Custom Search failed for %s | error=%s", query.text, e)
                return []

        sources: List[Source] = []
        for item in data.get("items", []) or []:
            link = item.get("link")
            if not link:
                continue
            title = item.get("title", "") or ""
            snippet = item.get("snippet", "") or ""
            published_at = self._extract_published_time(item)
            source_type = self._classify_source(link)
            sources.append(
                Source(
                    url=link,
                    type=source_type,
                    title=title,
                    description=snippet,
                    last_accessed=now,
                    published_at=published_at,
                    is_fresh=True,
                )
            )

        sources = self.deduplicate_sources(sources)
        self.cache[cache_key] = (datetime.utcnow(), sources)
        return sources

    async def search_candidate_info(self, query: FreshSearchQuery) -> List[Source]:
        """Search for candidate-specific information (kept for compatibility)."""
        issue = self._pick_issue("GENERAL")
        return await self.search_google_custom(query, issue)

    async def search_general(self, query: FreshSearchQuery) -> List[Source]:
        """Perform a general search without requiring a specific canonical issue."""
        issue = self._pick_issue("GENERAL")
        return await self.search_google_custom(query, issue)

    # ------------------------- query generation ------------------------- #

    def generate_issue_query(
        self,
        race_id: str,
        issue: CanonicalIssue,
        candidate_names: List[str] = None,
        state: str = None,
        office: str = None,
    ) -> FreshSearchQuery:
        """Generate a targeted search query for a specific issue."""
        query_parts = [issue.value]

        if state:
            query_parts.append(state)
        if office:
            query_parts.append(office)

        if candidate_names:
            candidates_part = " OR ".join(f'"{name}"' for name in candidate_names[:3])
            query_parts.append(f"({candidates_part})")

        query_text = " ".join(query_parts)
        query_text += " -site:wikipedia.org -site:reddit.com -site:twitter.com"

        return FreshSearchQuery(
            text=query_text,
            race_id=race_id,
            issue=issue,
            generated_at=datetime.utcnow(),
        )

    def generate_candidate_query(self, race_id: str, candidate_name: str) -> FreshSearchQuery:
        """Generate a search query specifically for a candidate."""
        parts = (race_id or "").split("-")
        state = parts[0] if len(parts) > 0 else ""
        office = parts[1] if len(parts) > 1 else ""
        query_text = f'"{candidate_name}" candidate {state} {office} -site:wikipedia.org -obituary -death'

        return FreshSearchQuery(
            text=query_text,
            race_id=race_id,
            issue=self._pick_issue("GENERAL"),
            generated_at=datetime.utcnow(),
        )

    def generate_candidate_issue_queries(
        self,
        race_id: str,
        candidate_name: str,
        issue: CanonicalIssue,
        race_metadata: Optional[RaceMetadata],
        sites: List[str],
    ) -> List[FreshSearchQuery]:
        """Generate base and site-specific queries for candidate×issue searches."""
        state = None
        year: Optional[str] = None
        district: Optional[str] = None

        if race_metadata:
            state = race_metadata.state
            year = str(race_metadata.year)
            district = race_metadata.district
        else:
            parts = race_id.split("-") if race_id else []
            if parts:
                state = parts[0]
            if len(parts) >= 3 and parts[-1].isdigit():
                year = parts[-1]

        issue_terms = [issue.value.lower()] + self.issue_synonyms.get(issue, [])
        issue_part = "(" + " OR ".join(issue_terms) + ")"

        base = f'"{candidate_name}" {issue_part}'
        if state:
            base += f" {state}"
        if district:
            base += f" {district}"
        if year:
            base += f" {year}"

        queries = [FreshSearchQuery(text=base, race_id=race_id, issue=issue, generated_at=datetime.utcnow())]
        for site in sites:
            queries.append(
                FreshSearchQuery(text=f"{base} site:{site}", race_id=race_id, issue=issue, generated_at=datetime.utcnow())
            )
        return queries

    def build_race_seed_queries(
        self,
        race_id: str,
        state: str,
        office: str,
        year: int,
        district: Optional[str],
        trusted_only: bool = True,
    ) -> List[FreshSearchQuery]:
        """Build a small set of seed queries for a race (trusted-first or permissive)."""
        state_part = state
        district_text = ""
        if district:
            district_text = " at-large" if str(district).upper() == "AL" else f" district {district}"

        targets = []
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
        for t in targets:
            out.append(
                FreshSearchQuery(
                    text=t,
                    race_id=race_id,
                    issue=self._pick_issue("GENERAL"),
                    generated_at=datetime.utcnow(),
                    max_results=10,
                    date_restrict="y2",
                    strict=True,  # enforce post-filter for seed
                )
            )
        return out

    # ------------------------- utilities ------------------------- #

    def deduplicate_sources(self, sources: List[Source]) -> List[Source]:
        """Remove duplicate sources based on scheme, netloc, and path."""
        seen: Set[str] = set()
        unique_sources: List[Source] = []

        for src in sources:
            parsed = urlparse(str(src.url))
            key = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"
            if key in seen:
                continue
            seen.add(key)
            unique_sources.append(src)

        return unique_sources

    # ------------------------- internal helpers ------------------------- #

    def _extract_published_time(self, item: Dict[str, Any]) -> Optional[datetime]:  # noqa: ANN401
        pagemap = item.get("pagemap", {}) or {}
        date_str: Optional[str] = None

        # Common metatags
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

        # Schema.org overlays
        if not date_str:
            if "newsarticle" in pagemap:
                date_str = (pagemap["newsarticle"][0] or {}).get("datepublished")
            elif "article" in pagemap:
                date_str = (pagemap["article"][0] or {}).get("datepublished")

        if not date_str:
            return None

        try:
            # Normalize trailing Z
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return None

    def _classify_source(self, url: str) -> SourceType:
        domain = urlparse(url).netloc.lower()
        if domain.endswith(".gov") or "fec.gov" in domain:
            return self._choose_type("GOVERNMENT")
        if any(social in domain for social in ["twitter.com", "facebook.com", "youtube.com", "tiktok.com"]):
            return self._choose_type("SOCIAL_MEDIA")
        if url.lower().endswith(".pdf"):
            return self._choose_type("PDF")
        return self._choose_type("WEBSITE")

    def _choose_type(self, preferred: str) -> SourceType:
        """Always return a valid SourceType, tolerating enum name drift across services."""
        if hasattr(SourceType, preferred):
            return getattr(SourceType, preferred)
        for alt in ("WEBSITE", "WEB", "URL", "ARTICLE", "UNKNOWN"):
            if hasattr(SourceType, alt):
                return getattr(SourceType, alt)
        try:
            return next(iter(SourceType))
        except Exception as e:  # noqa: BLE001
            raise AttributeError("SourceType enum has no accessible members") from e

    def _pick_issue(self, preferred: str = "GENERAL") -> CanonicalIssue:
        """Pick a valid CanonicalIssue, tolerating missing members."""
        if hasattr(CanonicalIssue, preferred):
            return getattr(CanonicalIssue, preferred)
        for alt in ("GENERAL_ELECTIONS", "DEFAULT"):
            if hasattr(CanonicalIssue, alt):
                return getattr(CanonicalIssue, alt)
        try:
            return next(iter(CanonicalIssue))
        except Exception as e:  # noqa: BLE001
            raise AttributeError("No usable CanonicalIssue enum member found") from e
