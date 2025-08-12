"""Search utilities for source discovery in SmarterVote Pipeline."""

import asyncio
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..schema import CanonicalIssue, FreshSearchQuery, RaceMetadata, Source, SourceType

logger = logging.getLogger(__name__)


class SearchUtils:
    """Utilities for performing searches to discover sources."""

    def __init__(self, search_config: dict):
        """Initialize with search configuration."""
        self.search_config = search_config
        self.cache: Dict[str, Tuple[datetime, List[Source]]] = {}
        self.cache_ttl = search_config.get("cache_ttl_seconds", 300)
        self.per_host_concurrency = search_config.get("per_host_concurrency", 5)
        self._host_semaphores: Dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(self.per_host_concurrency))

        # Basic domain trust ranking
        self.domain_trust: Dict[str, float] = {
            "gov": 1.0,
            "edu": 0.9,
            "fec.gov": 0.95,
            "ballotpedia.org": 0.9,
            "opensecrets.org": 0.9,
        }

        # Canonical issue synonyms
        self.issue_synonyms: Dict[CanonicalIssue, List[str]] = {
            CanonicalIssue.HEALTHCARE: [
                "health care",
                "medical",
                "medicare",
                "medicaid",
            ],
            CanonicalIssue.ECONOMY: [
                "economic",
                "jobs",
                "employment",
                "taxes",
                "budget",
            ],
            CanonicalIssue.CLIMATE_ENERGY: [
                "climate change",
                "environment",
                "renewable energy",
                "fossil fuels",
            ],
            CanonicalIssue.REPRODUCTIVE_RIGHTS: [
                "abortion",
                "reproductive health",
                "family planning",
            ],
            CanonicalIssue.IMMIGRATION: ["border", "refugees", "citizenship", "visa"],
            CanonicalIssue.GUNS_SAFETY: [
                "gun control",
                "firearms",
                "second amendment",
                "gun violence",
            ],
            CanonicalIssue.FOREIGN_POLICY: [
                "international",
                "defense",
                "military",
                "diplomacy",
            ],
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
            CanonicalIssue.TECH_AI: [
                "technology",
                "artificial intelligence",
                "privacy",
                "internet",
            ],
            CanonicalIssue.ELECTION_REFORM: [
                "voting rights",
                "gerrymandering",
                "campaign finance",
            ],
        }

    async def search_google_custom(self, query: FreshSearchQuery, issue: CanonicalIssue) -> List[Source]:
        """Perform Google Custom Search with caching, concurrency and scoring."""

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
            logger.info(f"Would search Google for: {query.text}")
            mock_source = Source(
                url=f"https://example.com/news/{issue.value.lower()}-{query.race_id}",
                type=SourceType.FRESH_SEARCH,
                title=f"Fresh: {issue.value} in {query.race_id}",
                description=f"Fresh search content about {issue.value} for this race",
                last_accessed=now,
                published_at=now,
                score=0.5,
                scoring_reason="mock",
                is_fresh=True,
            )
            self.cache[cache_key] = (now, [mock_source])
            return [mock_source]

        logger.info(f"Searching Google Custom Search for: {query.text}")

        try:
            import httpx
        except ImportError:
            logger.warning("httpx not available for Google search. Using mock results.")
            mock_source = Source(
                url=f"https://example.com/mock/{issue.value.lower()}-{query.race_id}",
                type=SourceType.FRESH_SEARCH,
                title=f"Mock: {issue.value} in {query.race_id}",
                description=f"Mock search content about {issue.value} for this race",
                last_accessed=now,
                published_at=now,
                score=0.5,
                scoring_reason="mock",
                is_fresh=True,
            )
            self.cache[cache_key] = (now, [mock_source])
            return [mock_source]

        search_url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": api_key,
            "cx": search_engine_id,
            "q": query.text,
            "num": self.search_config.get("max_results_per_query", 10),
            "dateRestrict": f"d{self.search_config.get('freshness_days', 30)}",
            "sort": "date",
        }

        host = urlparse(search_url).netloc
        async with self._host_semaphores[host]:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(search_url, params=params)
                    response.raise_for_status()
                    data = response.json()

            except Exception as e:  # noqa: BLE001
                logger.error(f"Google Custom Search failed: {e}")
                return []

        sources: List[Source] = []
        state = query.race_id.split("-")[0] if query.race_id else None
        for item in data.get("items", []):
            published_at = self._extract_published_time(item)
            source_type = self._classify_source(item["link"])
            score, reason = self._score_source(
                item["link"],
                item.get("title", ""),
                item.get("snippet", ""),
                published_at,
                state,
            )
            source = Source(
                url=item["link"],
                type=source_type,
                title=item.get("title"),
                description=item.get("snippet", ""),
                last_accessed=now,
                published_at=published_at,
                score=score,
                scoring_reason=reason,
                is_fresh=True,
            )
            sources.append(source)

        sources.sort(key=lambda s: s.score or 0, reverse=True)
        self.cache[cache_key] = (datetime.utcnow(), sources)
        return sources

    async def search_candidate_info(self, query: FreshSearchQuery) -> List[Source]:
        """
        Search for candidate-specific information.

        TODO:
        - [ ] Add social media profile discovery
        - [ ] Implement campaign website detection
        - [ ] Add financial disclosure search
        - [ ] Support for video/podcast discovery
        """
        # For now, use Google Custom Search with candidate-specific queries
        # This will be expanded to include specialized candidate information sources
        return await self.search_google_custom(query, CanonicalIssue.GENERAL)

    async def search_general(self, query: FreshSearchQuery) -> List[Source]:
        """
        Perform a general search without requiring a specific canonical issue.
        
        Args:
            query: Search query object
            
        Returns:
            List of search results as Source objects
        """
        return await self.search_google_custom(query, CanonicalIssue.GENERAL)

    def generate_issue_query(
        self,
        race_id: str,
        issue: CanonicalIssue,
        candidate_names: List[str] = None,
        state: str = None,
        office: str = None,
    ) -> FreshSearchQuery:
        """
        Generate a targeted search query for a specific issue.

        Args:
            race_id: Race identifier like 'mo-senate-2024'
            issue: The canonical issue to search for
            candidate_names: Optional list of candidate names to include
            state: Optional state to include in search
            office: Optional office type to include

        Returns:
            FreshSearchQuery optimized for the issue
        """
        # Start with the issue itself
        query_parts = [issue.value]

        # Add race/location context
        if state:
            query_parts.append(state)
        if office:
            query_parts.append(office)

        # Add candidate names for personalized searches
        if candidate_names:
            # Create a query that includes candidates
            candidates_part = " OR ".join(f'"{name}"' for name in candidate_names[:3])  # Limit to top 3
            query_parts.append(f"({candidates_part})")

        # Create search text
        query_text = " ".join(query_parts)

        # Add search operators for better results
        query_text += " -site:wikipedia.org -site:reddit.com -site:twitter.com"

        return FreshSearchQuery(
            text=query_text,
            race_id=race_id,
            issue=issue,
            generated_at=datetime.utcnow(),
        )

    def generate_candidate_query(self, race_id: str, candidate_name: str) -> FreshSearchQuery:
        """
        Generate a search query specifically for a candidate.

        TODO:
        - [ ] Add candidate-specific search terms (positions, endorsements, etc.)
        - [ ] Include negative search terms to filter out irrelevant content
        - [ ] Add temporal constraints for recent information
        """
        query_text = f'"{candidate_name}" candidate {race_id.split("-")[0]} {race_id.split("-")[1]}'
        query_text += " -site:wikipedia.org -obituary -death"

        return FreshSearchQuery(
            text=query_text,
            race_id=race_id,
            issue=CanonicalIssue.GENERAL,
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
        year = None
        district = None
        if race_metadata:
            state = race_metadata.state
            year = race_metadata.year
            district = race_metadata.district
        else:
            parts = race_id.split("-")
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

        queries = [
            FreshSearchQuery(
                text=base,
                race_id=race_id,
                issue=issue,
                generated_at=datetime.utcnow(),
            )
        ]

        for site in sites:
            queries.append(
                FreshSearchQuery(
                    text=f"{base} site:{site}",
                    race_id=race_id,
                    issue=issue,
                    generated_at=datetime.utcnow(),
                )
            )

        return queries

    def deduplicate_sources(self, sources: List[Source]) -> List[Source]:
        """Remove duplicate sources with aggressive URL normalization."""

        seen: Set[str] = set()
        seen_titles: Set[str] = set()
        unique_sources: List[Source] = []

        for src in sources:
            normalized = self._normalize_url(str(src.url))
            title_key = urlparse(normalized).netloc + "|" + re.sub(r"\s+", " ", (src.title or "").lower())
            if normalized in seen or title_key in seen_titles:
                continue
            seen.add(normalized)
            seen_titles.add(title_key)
            unique_sources.append(src)

        return unique_sources

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("m."):
            netloc = netloc[2:]

        path = re.sub(r"/(amp|mobile|print)/?", "/", parsed.path)
        query = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not k.lower().startswith(("utm_", "gclid", "fbclid"))
        ]
        normalized = urlunparse(
            (
                parsed.scheme,
                netloc,
                path.rstrip("/"),
                "",
                urlencode(query),
                "",
            )
        )
        return normalized

    def _extract_published_time(self, item: Dict[str, Any]) -> Optional[datetime]:  # noqa: ANN401
        pagemap = item.get("pagemap", {})
        date_str = None
        if "metatags" in pagemap:
            for tag in pagemap["metatags"]:
                date_str = tag.get("article:published_time") or tag.get("pubdate")
                if date_str:
                    break
        if not date_str and "newsarticle" in pagemap:
            date_str = pagemap["newsarticle"][0].get("datepublished")
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return None

    def _classify_source(self, url: str) -> SourceType:
        domain = urlparse(url).netloc.lower()
        if domain.endswith(".gov") or "fec.gov" in domain:
            return SourceType.GOVERNMENT
        if any(social in domain for social in ["twitter.com", "facebook.com", "youtube.com"]):
            return SourceType.SOCIAL_MEDIA
        if url.lower().endswith(".pdf"):
            return SourceType.PDF
        return SourceType.WEBSITE

    def _score_source(
        self,
        url: str,
        title: str,
        snippet: str,
        published_at: Optional[datetime],
        state: Optional[str],
    ) -> Tuple[float, str]:
        domain = urlparse(url).netloc.lower()
        reason = []

        # Domain trust
        trust = 0.5
        if domain.endswith(".gov") or "fec.gov" in domain:
            trust = 1.0
            reason.append("trust=gov")
        elif domain.endswith(".edu"):
            trust = 0.9
            reason.append("trust=edu")
        elif any(k in domain for k in ["ballotpedia.org", "opensecrets.org"]):
            trust = 0.8
            reason.append("trust=org")
        else:
            reason.append("trust=other")

        score = trust

        # Freshness
        fresh_window = self.search_config.get("freshness_days", 30)
        if published_at:
            if (datetime.utcnow() - published_at).days <= fresh_window:
                score += 0.1
                reason.append("fresh=Y")
            else:
                reason.append("fresh=N")
        else:
            reason.append("fresh=?")

        # Localness
        local = 0.0
        if state:
            state_l = state.lower()
            if state_l in url.lower() or state_l in title.lower() or state_l in snippet.lower():
                local = 0.1
        reason.append(f"local={local}")
        score += local

        # Type bonus
        source_type = self._classify_source(url)
        if source_type in {SourceType.GOVERNMENT, SourceType.PDF}:
            score += 0.1
        reason.append(f"type={source_type.value}")

        return min(score, 1.0), "; ".join(reason)
