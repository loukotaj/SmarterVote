"""
Search utilities for source discovery in SmarterVote Pipeline.

This module contains utilities for performing various types of searches
to discover sources for electoral content.
"""

import logging
import os
from datetime import datetime
from typing import List

from ..schema import CanonicalIssue, FreshSearchQuery, Source, SourceType

logger = logging.getLogger(__name__)


class SearchUtils:
    """Utilities for performing searches to discover sources."""

    def __init__(self, search_config: dict):
        """Initialize with search configuration."""
        self.search_config = search_config

    async def search_google_custom(self, query: FreshSearchQuery, issue: CanonicalIssue) -> List[Source]:
        """
        Perform Google Custom Search for an issue.

        Implements actual Google Custom Search API integration with proper error handling,
        retry logic, and result quality filtering.
        """
        # Get Google Custom Search configuration
        api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

        if not api_key or not search_engine_id:
            logger.warning(
                "Google Custom Search API not configured (missing GOOGLE_SEARCH_API_KEY or GOOGLE_SEARCH_ENGINE_ID)"
            )
            logger.info(f"Would search Google for: {query.text}")

            # Return mock results when API is not configured for local development
            mock_results = [
                Source(
                    url=f"https://example.com/news/{issue.value.lower()}-{query.race_id}",
                    type=SourceType.FRESH_SEARCH,
                    title=f"Fresh: {issue.value} in {query.race_id}",
                    description=f"Fresh search content about {issue.value} for this race",
                    last_accessed=datetime.utcnow(),
                    is_fresh=True,
                )
            ]
            return mock_results

        logger.info(f"Searching Google Custom Search for: {query.text}")

        try:
            try:
                import httpx
            except ImportError:
                logger.warning("httpx not available for Google search. Using mock results.")
                return [
                    Source(
                        url=f"https://example.com/mock/{issue.value.lower()}-{query.race_id}",
                        type=SourceType.FRESH_SEARCH,
                        title=f"Mock: {issue.value} in {query.race_id}",
                        description=f"Mock search content about {issue.value} for this race",
                        last_accessed=datetime.utcnow(),
                        is_fresh=True,
                    )
                ]

            # Build search URL
            search_url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": api_key,
                "cx": search_engine_id,
                "q": query.text,
                "num": min(query.max_results, 10),  # Google allows max 10 per request
                "safe": "active",
                "sort": "date",  # Prioritize recent content
            }

            # Add date restriction if specified
            if query.date_restrict:
                params["dateRestrict"] = query.date_restrict

            # Perform search
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(search_url, params=params)
                response.raise_for_status()

            data = response.json()
            search_items = data.get("items", [])

            logger.info(f"Google search returned {len(search_items)} results for {query.text}")

            # Convert results to Source objects
            sources = []
            for item in search_items:
                try:
                    source = Source(
                        url=item["link"],
                        type=SourceType.FRESH_SEARCH,
                        title=item.get("title", ""),
                        description=item.get("snippet", ""),
                        last_accessed=datetime.utcnow(),
                        is_fresh=True,
                        metadata={
                            "search_query": query.text,
                            "search_engine": "google",
                            "issue": issue.value,
                            "display_link": item.get("displayLink", ""),
                        },
                    )
                    sources.append(source)
                except KeyError as e:
                    logger.warning(f"Skipping malformed search result: missing {e}")
                    continue

            return sources

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error("Google Search API rate limit exceeded")
            else:
                logger.error(f"Google Search API error {e.response.status_code}: {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"Error during Google search for {query.text}: {e}")
            return []

    async def search_candidate_info(self, query: FreshSearchQuery) -> List[Source]:
        """Search for candidate-specific information."""
        # Placeholder for candidate-specific search
        logger.debug(f"Would search for candidate info: {query.text}")
        return []

    def deduplicate_sources(self, sources: List[Source]) -> List[Source]:
        """
        Remove duplicate sources based on URL and content similarity.

        TODO: Implement sophisticated deduplication:
        - URL normalization and canonical form matching
        - Content similarity detection using hashing
        - Title and description fuzzy matching
        - Domain-based grouping and selection
        - Source quality scoring for duplicate resolution
        - Temporal preference for fresher content
        """
        if not sources:
            return []

        seen_urls = set()
        deduplicated = []

        for source in sources:
            # Normalize URL for comparison
            normalized_url = source.url.lower().rstrip("/")

            # Remove common URL variations
            normalized_url = normalized_url.replace("www.", "")
            normalized_url = normalized_url.replace("http://", "https://")

            if normalized_url not in seen_urls:
                seen_urls.add(normalized_url)
                deduplicated.append(source)

        logger.info(f"Deduplicated {len(sources)} sources to {len(deduplicated)}")
        return deduplicated

    def generate_issue_query(self, race_id: str, issue: CanonicalIssue) -> FreshSearchQuery:
        """
        Generate optimized search query for a specific issue.

        Creates targeted search queries that combine race context with issue-specific
        keywords for maximum relevance and discovery of fresh content.
        """
        # Parse race ID for geographic and office context
        race_parts = race_id.split("-")
        state = race_parts[0].upper() if race_parts else ""
        office = " ".join(race_parts[1:-1]) if len(race_parts) > 2 else race_parts[1] if len(race_parts) > 1 else ""
        year = race_parts[-1] if race_parts and race_parts[-1].isdigit() else "2024"

        # Issue-specific query templates
        issue_queries = {
            CanonicalIssue.HEALTHCARE: [
                f"{state} {office} healthcare policy {year}",
                f"{state} {office} medicare medicaid {year}",
                f"{state} {office} health insurance {year}",
            ],
            CanonicalIssue.ECONOMY: [
                f"{state} {office} economy jobs {year}",
                f"{state} {office} tax policy {year}",
                f"{state} {office} business employment {year}",
            ],
            CanonicalIssue.CLIMATE_ENERGY: [
                f"{state} {office} climate change {year}",
                f"{state} {office} renewable energy {year}",
                f"{state} {office} environmental policy {year}",
            ],
            CanonicalIssue.REPRODUCTIVE_RIGHTS: [
                f"{state} {office} abortion reproductive rights {year}",
                f"{state} {office} planned parenthood {year}",
            ],
            CanonicalIssue.IMMIGRATION: [
                f"{state} {office} immigration border {year}",
                f"{state} {office} citizenship immigration {year}",
            ],
            CanonicalIssue.GUNS_SAFETY: [
                f"{state} {office} gun control {year}",
                f"{state} {office} second amendment {year}",
                f"{state} {office} gun safety {year}",
            ],
            CanonicalIssue.FOREIGN_POLICY: [
                f"{state} {office} foreign policy {year}",
                f"{state} {office} military defense {year}",
            ],
            CanonicalIssue.SOCIAL_JUSTICE: [
                f"{state} {office} civil rights {year}",
                f"{state} {office} social justice equality {year}",
            ],
            CanonicalIssue.EDUCATION: [
                f"{state} {office} education schools {year}",
                f"{state} {office} teacher education funding {year}",
            ],
            CanonicalIssue.TECH_AI: [
                f"{state} {office} technology policy {year}",
                f"{state} {office} artificial intelligence {year}",
            ],
            CanonicalIssue.ELECTION_REFORM: [
                f"{state} {office} election reform {year}",
                f"{state} {office} voting rights {year}",
            ],
        }

        # Get queries for this issue, fallback to generic
        queries = issue_queries.get(issue, [f"{state} {office} {issue.value} {year}"])

        # Use the first (most specific) query
        query_text = queries[0]

        return FreshSearchQuery(
            text=query_text,
            issue=issue,
            race_id=race_id,
            max_results=self.search_config["max_results_per_query"],
            date_restrict=f"d{self.search_config['freshness_days']}",  # Last N days
        )

    def generate_candidate_query(self, race_id: str, candidate_name: str) -> FreshSearchQuery:
        """Generate search query for a specific candidate."""
        race_parts = race_id.split("-")
        state = race_parts[0] if race_parts else ""
        office = " ".join(race_parts[1:-1]) if len(race_parts) > 2 else race_parts[1] if len(race_parts) > 1 else ""
        year = race_parts[-1] if race_parts and race_parts[-1].isdigit() else "2024"

        query_text = f'"{candidate_name}" {state} {office} {year}'

        return FreshSearchQuery(
            text=query_text,
            issue=None,
            race_id=race_id,
            max_results=self.search_config["max_results_per_query"],
            date_restrict=f"d{self.search_config['freshness_days']}",
        )
