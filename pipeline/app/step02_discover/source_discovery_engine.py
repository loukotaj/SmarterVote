"""
Source Discovery Engine for SmarterVote Pipeline

This module handles discovering data sources about electoral races including:
- Seed URL discovery from known databases (Ballotpedia, FEC, etc.)
- Google Custom Search for fresh issue-specific content
- Social media platform discovery
- News outlet searches

TODO: Implement the following features:
- [ ] Add support for more electoral data sources (Vote411, OpenSecrets)
- [ ] Implement intelligent query generation for Google searches
- [ ] Add rate limiting and quota management for search APIs
- [ ] Support for discovering candidate social media accounts
- [ ] Add RSS feed discovery for news sources
- [ ] Implement source quality scoring and filtering
- [ ] Add geographic filtering for local news sources
- [ ] Support for discovering debate transcripts and videos
- [ ] Add campaign finance data source discovery
- [ ] Implement duplicate source detection and deduplication
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from ..schema import CanonicalIssue, RaceJSON, RaceMetadata, Source, SourceType
from ..utils.search_utils import SearchUtils

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
            "top_results_per_query": 5,
            "num_queries_per_candidate": 15,
            "freshness_days": 30,
            "quality_threshold": 0.7,
            "candidate_cap": 5,
            "issues": [
                CanonicalIssue.HEALTHCARE,
                CanonicalIssue.ECONOMY,
                CanonicalIssue.IMMIGRATION,
            ],
            "general_issue_terms": [
                CanonicalIssue.HEALTHCARE,
                CanonicalIssue.ECONOMY,
            ],
            "per_host_concurrency": 5,
            "cache_ttl_seconds": 300,
        }
        # Initialize search utilities
        self.search_utils = SearchUtils(self.search_config)

    async def discover_all_sources(self, race_id: str, race_json: Optional[RaceJSON] = None) -> List[Source]:
        """
        Discover all sources for a race including seed sources and fresh issue searches.

        Args:
            race_id: Race identifier like 'mo-senate-2024'
            race_json: Optional RaceJSON for optimized discovery

        Returns:
            List of all discovered sources (seed + fresh)
        """
        logger.info(f"Starting comprehensive source discovery for {race_id}")

        if race_json and race_json.race_metadata:
            rm = race_json.race_metadata
            logger.info(f"Using race metadata: {rm.full_office_name} in {rm.jurisdiction}")
        else:
            rm = None

        # Get seed sources
        seed_sources = await self.discover_seed_sources(race_id, rm)
        logger.info(f"Found {len(seed_sources)} seed sources")

        # Get fresh issue-specific sources
        fresh_sources = await self.discover_fresh_issue_sources(race_id, race_json)
        logger.info(f"Found {len(fresh_sources)} fresh issue sources")

        # Combine and deduplicate
        all_sources = seed_sources + fresh_sources
        deduplicated = self.search_utils.deduplicate_sources(all_sources)

        logger.info(f"Total sources after deduplication: {len(deduplicated)}")
        return deduplicated

    async def discover_seed_sources(self, race_id: str, race_metadata: Optional[RaceMetadata] = None) -> List[Source]:
        """
        Discover seed sources for a race from known electoral databases.

        Args:
            race_id: Race identifier like 'mo-senate-2024'
            race_metadata: Optional race metadata for targeted discovery

        Returns:
            List of seed sources
        """
        return await self._discover_seed_sources(race_id, race_metadata)

    async def discover_fresh_issue_sources(self, race_id: str, race_json: Optional[RaceJSON] = None) -> List[Source]:
        """Discover fresh issue-specific sources using Google Custom Search."""

        return await self._discover_fresh_issue_sources(race_id, race_json)

    async def _discover_seed_sources(self, race_id: str, race_metadata: Optional[RaceMetadata] = None) -> List[Source]:
        """
        Discover sources from known electoral databases.

        TODO:
        - [ ] Add specific URL construction for each database
        - [ ] Implement API integrations where available
        - [ ] Add error handling for unavailable sources
        - [ ] Support for different race types (federal, state, local)
        """
        sources = []

        # Use metadata if available, otherwise parse race_id
        if race_metadata:
            state = race_metadata.state
            office_type = race_metadata.office_type
            year = race_metadata.year
            district = race_metadata.district
            race_type = race_metadata.race_type
        else:
            # Fallback to parsing race_id
            race_parts = race_id.split("-")
            if len(race_parts) >= 3:
                state = race_parts[0].upper()
                office_type = race_parts[1]
                year = int(race_parts[2]) if race_parts[2].isdigit() else int(race_parts[-1])
                district = race_parts[2] if len(race_parts) == 4 and race_parts[2].isdigit() else None
                race_type = "federal" if office_type in ["senate", "house"] else "state"
            else:
                logger.warning(f"Could not parse race_id {race_id}, using minimal sources")
                return sources

        # Ballotpedia URL construction (enhanced with metadata)
        if district:
            ballotpedia_url = f"https://ballotpedia.org/{year}_{state}_{office_type}_district_{district}_election"
        else:
            ballotpedia_url = f"https://ballotpedia.org/{year}_{state}_{office_type}_election"

        sources.append(
            Source(
                url=ballotpedia_url,
                type=SourceType.GOVERNMENT,
                title=f"Ballotpedia - {state} {office_type.title()} Election {year}",
                description="Official election information from Ballotpedia",
                last_accessed=datetime.utcnow(),
                is_fresh=False,
            )
        )

        # Federal races get additional federal sources
        if race_type == "federal":
            # FEC data for federal races
            if office_type == "senate":
                fec_url = f"https://www.fec.gov/data/elections/senate/{state.lower()}/{year}/"
            elif office_type == "house" and district:
                fec_url = f"https://www.fec.gov/data/elections/house/{state.lower()}/{district}/{year}/"
            else:
                fec_url = f"https://www.fec.gov/data/elections/{office_type.lower()}/{state.lower()}/{year}/"

            sources.append(
                Source(
                    url=fec_url,
                    type=SourceType.GOVERNMENT,
                    title=f"FEC - {state} {office_type.title()} Election {year}",
                    description="Federal Election Commission data",
                    last_accessed=datetime.utcnow(),
                    is_fresh=False,
                )
            )

            # OpenSecrets for campaign finance
            opensecrets_url = f"https://www.opensecrets.org/races/summary?cycle={year}&id={state}{district or ''}&spec=N"
            sources.append(
                Source(
                    url=opensecrets_url,
                    type=SourceType.GOVERNMENT,
                    title=f"OpenSecrets - {state} {office_type.title()} Campaign Finance",
                    description="Campaign finance data from OpenSecrets",
                    last_accessed=datetime.utcnow(),
                    is_fresh=False,
                )
            )

        # State-specific sources for state races
        elif race_type == "state":
            # Secretary of State election pages (varies by state)
            sos_url = f"https://www.sos.{state.lower()}.gov/elections/{year}"
            sources.append(
                Source(
                    url=sos_url,
                    type=SourceType.GOVERNMENT,
                    title=f"{state} Secretary of State - Elections",
                    description=f"Official {state} election information",
                    last_accessed=datetime.utcnow(),
                    is_fresh=False,
                )
            )

        logger.info(f"Generated {len(sources)} seed sources for {race_id}")
        return sources

    async def _discover_fresh_issue_sources(self, race_id: str, race_json: Optional[RaceJSON] = None) -> List[Source]:
        """Run candidate×issue searches concurrently and rank results."""

        issues = self.search_config.get("issues", list(CanonicalIssue))
        candidate_cap = self.search_config.get("candidate_cap", 3)
        query_limit = self.search_config.get("num_queries_per_candidate", 15)
        top_results = self.search_config.get("top_results_per_query", 5)

        if race_json and race_json.candidates:
            candidates = [c.name for c in race_json.candidates][:candidate_cap]
            race_meta = race_json.race_metadata
        else:
            candidates = (await self._extract_candidate_names(race_id))[:candidate_cap]
            race_meta = race_json.race_metadata if race_json else None

        all_sources: List[Source] = []
        for cand in candidates:
            queries = self.search_utils.generate_candidate_issue_queries(race_id, cand, issues, race_meta, query_limit)
            tasks = [self.search_utils.search_google_custom(q, q.issue) for q in queries]
            results = await asyncio.gather(*tasks) if tasks else []
            sources = [s for r in results for s in r]
            deduped = self.search_utils.deduplicate_sources(sources)
            all_sources.extend(sorted(deduped, key=lambda s: s.score or 0, reverse=True))

        general_issues = self.search_config.get("general_issue_terms", [])
        for issue in general_issues:
            q = self.search_utils.generate_issue_query(
                race_id,
                issue,
                state=getattr(race_meta, "state", None),
                office=getattr(race_meta, "office_type", None),
            )
            q.max_results = top_results
            all_sources.extend(await self.search_utils.search_google_custom(q, issue))

        deduped_all = self.search_utils.deduplicate_sources(all_sources)
        return sorted(deduped_all, key=lambda s: s.score or 0, reverse=True)

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
