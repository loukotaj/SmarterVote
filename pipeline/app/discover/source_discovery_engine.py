"""
Source Discovery Engine for SmarterVote Pipeline

This module handles the discovery of data sources about electoral races.
It combines seed sources from known databases with fresh search results
to build a comprehensive source base for content extraction.
"""

import asyncio
import logging
from typing import List

from ..schema import CanonicalIssue, Source, SourceType
from .search_utils import SearchUtils

logger = logging.getLogger(__name__)


class SourceDiscoveryEngine:
    """Engine for discovering data sources about electoral races."""

    def __init__(self):
        self.seed_sources = {
            "ballotpedia": "https://ballotpedia.org",
            "fec": "https://www.fec.gov",
            "propublica": "https://www.propublica.org",
            "opensecrets": "https://www.opensecrets.org",
            "vote411": "https://www.vote411.org",
            "govtrack": "https://www.govtrack.us",
            "congress_gov": "https://www.congress.gov",
        }

        # TODO: Move to configuration
        self.search_config = {
            "max_results_per_query": 10,
            "freshness_days": 30,
            "quality_threshold": 0.7,
            "enable_social_media": True,
            "enable_news_search": True,
        }

        # Initialize search utilities
        self.search_utils = SearchUtils(self.search_config)

    async def discover_all_sources(self, race_id: str) -> List[Source]:
        """
        Discover all sources for a race including seed sources and fresh issue searches.

        Args:
            race_id: Race identifier like 'mo-senate-2024'

        Returns:
            List of all discovered sources (seed + fresh)
        """
        logger.info(f"Starting comprehensive source discovery for {race_id}")

        # Get seed sources
        seed_sources = await self.discover_seed_sources(race_id)
        logger.info(f"Found {len(seed_sources)} seed sources")

        # Get fresh issue-specific sources
        fresh_sources = await self.discover_fresh_issue_sources(race_id)
        logger.info(f"Found {len(fresh_sources)} fresh issue sources")

        # Combine and deduplicate
        all_sources = seed_sources + fresh_sources
        deduplicated = self.search_utils.deduplicate_sources(all_sources)

        logger.info(f"Total sources after deduplication: {len(deduplicated)}")
        return deduplicated

    async def discover_seed_sources(self, race_id: str) -> List[Source]:
        """
        Discover seed sources for a race from known electoral databases.

        Args:
            race_id: Race identifier like 'mo-senate-2024'

        Returns:
            List of seed sources
        """
        return await self._discover_seed_sources(race_id)

    async def discover_fresh_issue_sources(self, race_id: str) -> List[Source]:
        """
        Discover fresh issue-specific sources using Google Custom Search.

        Args:
            race_id: Race identifier like 'mo-senate-2024'

        Returns:
            List of fresh sources organized by issue
        """
        return await self._discover_fresh_issue_sources(race_id)

    async def _discover_seed_sources(self, race_id: str) -> List[Source]:
        """
        Discover seed sources from known electoral databases.

        TODO: Implement actual API integration with:
        - Ballotpedia API for candidate and race information
        - FEC API for campaign finance data
        - ProPublica Congress API for voting records
        - OpenSecrets API for lobbying and donor data
        - Vote411 League of Women Voters data
        - GovTrack API for legislative information
        - Congress.gov API for bill and vote data
        """
        sources = []

        # Parse race information
        race_parts = race_id.split("-")
        state = race_parts[0].upper() if race_parts else "US"
        office = race_parts[1] if len(race_parts) > 1 else "unknown"
        year = race_parts[2] if len(race_parts) > 2 else "2024"

        logger.info(f"Discovering seed sources for {state} {office} {year}")

        # Generate seed source URLs based on race information
        try:
            # Ballotpedia
            ballotpedia_url = f"https://ballotpedia.org/{state}_{office}_{year}"
            sources.append(
                Source(
                    url=ballotpedia_url,
                    type=SourceType.GOVERNMENT,
                    title=f"Ballotpedia: {state} {office} {year}",
                    description=f"Official race information for {state} {office} election",
                    is_fresh=False,
                )
            )

            # FEC (for federal races)
            if office.lower() in ["senate", "house", "president"]:
                fec_url = f"https://www.fec.gov/data/elections/{office.lower()}/{state.lower()}/{year}/"
                sources.append(
                    Source(
                        url=fec_url,
                        type=SourceType.GOVERNMENT,
                        title=f"FEC: {state} {office} {year}",
                        description=f"Federal Election Commission data for {state} {office}",
                        is_fresh=False,
                    )
                )

            # OpenSecrets (for campaign finance)
            opensecrets_url = f"https://www.opensecrets.org/races/summary?cycle={year}&id={state}{office[0]}00"
            sources.append(
                Source(
                    url=opensecrets_url,
                    type=SourceType.API,
                    title=f"OpenSecrets: {state} {office} {year}",
                    description=f"Campaign finance data for {state} {office}",
                    is_fresh=False,
                )
            )

        except Exception as e:
            logger.warning(f"Error generating seed sources for {race_id}: {e}")

        logger.info(f"Generated {len(sources)} seed sources for {race_id}")
        return sources

    async def _discover_fresh_issue_sources(self, race_id: str) -> List[Source]:
        """
        Discover fresh issue-specific sources using search APIs.

        Performs targeted searches for each canonical issue to find recent
        news, analysis, and candidate statements.
        """
        all_sources = []

        # Get all canonical issues
        canonical_issues = list(CanonicalIssue)

        logger.info(f"Searching for fresh sources across {len(canonical_issues)} issues")

        # Search for each issue in parallel (with concurrency limit)
        semaphore = asyncio.Semaphore(3)  # Limit concurrent searches
        
        async def search_issue(issue: CanonicalIssue) -> List[Source]:
            async with semaphore:
                try:
                    query = self.search_utils.generate_issue_query(race_id, issue)
                    return await self.search_utils.search_google_custom(query, issue)
                except Exception as e:
                    logger.error(f"Error searching for {issue.value}: {e}")
                    return []

        # Execute searches in parallel
        search_tasks = [search_issue(issue) for issue in canonical_issues]
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Collect results
        for i, result in enumerate(search_results):
            issue = canonical_issues[i]
            if isinstance(result, Exception):
                logger.error(f"Search failed for {issue.value}: {result}")
                continue
            
            if isinstance(result, list):
                all_sources.extend(result)
                logger.info(f"Found {len(result)} sources for {issue.value}")

        logger.info(f"Total fresh sources discovered: {len(all_sources)}")
        return all_sources

    async def _discover_candidate_sources(self, race_id: str) -> List[Source]:
        """
        Discover candidate-specific sources (websites, social media, etc.).

        Implements candidate name extraction and targeted search for candidate information.
        """
        sources = []

        try:
            # First, try to get candidate names from seed sources or a basic search
            candidate_names = await self._extract_candidate_names(race_id)

            for candidate_name in candidate_names:
                logger.info(f"Discovering sources for candidate: {candidate_name}")

                # Search for candidate-specific information
                candidate_query = self.search_utils.generate_candidate_query(race_id, candidate_name)
                candidate_sources = await self.search_utils.search_candidate_info(candidate_query)
                sources.extend(candidate_sources)

        except Exception as e:
            logger.warning(f"Error discovering candidate sources for {race_id}: {e}")

        logger.info(f"Found {len(sources)} candidate-specific sources for {race_id}")
        return sources

    async def _extract_candidate_names(self, race_id: str) -> List[str]:
        """
        Extract candidate names from basic race information.

        This is a simplified implementation that generates likely candidate names
        for testing. In production, this would query Ballotpedia or other sources.
        """
        # Parse race info
        race_parts = race_id.split("-")
        state = race_parts[0].upper() if race_parts else "XX"
        office = race_parts[1] if len(race_parts) > 1 else "office"

        # For now, return some common candidate patterns for testing
        # In production, this would query actual candidate data
        candidate_names = [
            f"Incumbent {office.title()}",
            f"Challenger {state}",
        ]

        logger.debug(f"Extracted candidate names for {race_id}: {candidate_names}")
        return candidate_names

    async def _discover_news_sources(self, race_id: str) -> List[Source]:
        """
        Discover news sources covering the race.

        TODO: Implement news source discovery:
        - Major national news outlets (CNN, Fox, NYT, WSJ, etc.)
        - State and local news sources
        - Political news sites (Politico, Roll Call, etc.)
        - Alternative and opinion sources
        - Podcast and video content
        - Social media trending topics
        """
        # Placeholder implementation
        logger.debug(f"Would discover news sources for {race_id}")
        return []