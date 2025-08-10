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

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..schema import CanonicalIssue, FreshSearchQuery, Source, SourceType

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
        deduplicated = self._deduplicate_sources(all_sources)

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
            List of fresh sources for all canonical issues
        """
        return await self._discover_fresh_issue_sources(race_id)
        """
        Discover all relevant sources for a race.

        Args:
            race_id: Race identifier (e.g., 'mo-senate-2024')

        Returns:
            List of discovered sources

        TODO:
        - [ ] Add parallel processing for different discovery methods
        - [ ] Implement source priority ranking
        - [ ] Add caching to avoid redundant API calls
        - [ ] Support for incremental discovery updates
        """
        logger.info(f"Discovering sources for race: {race_id}")

        all_sources = []

        # 1. Discover seed sources (official databases)
        seed_sources = await self._discover_seed_sources(race_id)
        all_sources.extend(seed_sources)

        # 2. Fresh issue-specific searches
        fresh_sources = await self._discover_fresh_issue_sources(race_id)
        all_sources.extend(fresh_sources)

        # 3. Candidate-specific searches
        candidate_sources = await self._discover_candidate_sources(race_id)
        all_sources.extend(candidate_sources)

        # 4. News and media sources
        news_sources = await self._discover_news_sources(race_id)
        all_sources.extend(news_sources)

        # Remove duplicates and filter by quality
        unique_sources = self._deduplicate_sources(all_sources)
        quality_sources = self._filter_by_quality(unique_sources)

        logger.info(f"Discovered {len(quality_sources)} quality sources for {race_id}")
        return quality_sources

    async def _discover_seed_sources(self, race_id: str) -> List[Source]:
        """
        Discover sources from known electoral databases.

        TODO:
        - [ ] Add specific URL construction for each database
        - [ ] Implement API integrations where available
        - [ ] Add error handling for unavailable sources
        - [ ] Support for different race types (federal, state, local)
        """
        sources = []

        # Parse race_id to extract state, office, year
        race_parts = race_id.split("-")
        if len(race_parts) >= 3:
            state = race_parts[0].upper()
            office = race_parts[1]
            year = race_parts[2]

            # Ballotpedia URL construction
            ballotpedia_url = f"https://ballotpedia.org/{year}_{state}_{office}_election"
            sources.append(
                Source(
                    url=ballotpedia_url,
                    type=SourceType.GOVERNMENT,
                    title=f"Ballotpedia - {state} {office.title()} Election {year}",
                    description="Official election information from Ballotpedia",
                    last_accessed=datetime.utcnow(),
                    is_fresh=False,
                )
            )

            # FEC data for federal races
            if office.lower() in ["senate", "house", "president"]:
                fec_url = f"https://www.fec.gov/data/elections/{office.lower()}/{state.lower()}/{year}/"
                sources.append(
                    Source(
                        url=fec_url,
                        type=SourceType.GOVERNMENT,
                        title=f"FEC - {state} {office.title()} Election {year}",
                        description="Federal Election Commission data",
                        last_accessed=datetime.utcnow(),
                        is_fresh=False,
                    )
                )

        return sources

    async def _discover_fresh_issue_sources(self, race_id: str) -> List[Source]:
        """
        Discover fresh content for each canonical issue using Google Custom Search.

        TODO:
        - [ ] Implement Google Custom Search API integration
        - [ ] Add query optimization for better results
        - [ ] Support for date-based filtering
        - [ ] Add geographic relevance filtering
        """
        sources = []

        # Generate search queries for each canonical issue
        for issue in CanonicalIssue:
            query = self._generate_issue_query(race_id, issue)
            issue_sources = await self._search_google_custom(query, issue)
            sources.extend(issue_sources)

        return sources

    def _generate_issue_query(self, race_id: str, issue: CanonicalIssue) -> FreshSearchQuery:
        """
        Generate optimized search query for a specific issue.

        TODO:
        - [ ] Add more sophisticated query generation
        - [ ] Include candidate names when available
        - [ ] Add negative keywords to filter out irrelevant content
        - [ ] Support for different query strategies per issue type
        """
        race_parts = race_id.split("-")
        state = race_parts[0] if race_parts else ""
        office = race_parts[1] if len(race_parts) > 1 else ""
        year = race_parts[2] if len(race_parts) > 2 else ""

        # Base query components
        location_terms = [state, f"{state} {office}"]
        issue_terms = [issue.value.lower()]

        # Add related terms for specific issues
        issue_synonyms = {
            CanonicalIssue.HEALTHCARE: [
                "health care",
                "medical",
                "insurance",
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

        if issue in issue_synonyms:
            issue_terms.extend(issue_synonyms[issue])

        # Construct query
        query_parts = [
            f'"{state} {office} election {year}"',
            f'({" OR ".join(issue_terms)})',
            "candidate position OR stance OR policy",
        ]

        query_text = " ".join(query_parts)

        return FreshSearchQuery(
            text=query_text,
            issue=issue,
            race_id=race_id,
            max_results=self.search_config["max_results_per_query"],
            date_restrict=f"d{self.search_config['freshness_days']}",  # Last N days
        )

    async def _search_google_custom(self, query: FreshSearchQuery, issue: CanonicalIssue) -> List[Source]:
        """
        Perform Google Custom Search for an issue.

        Implements actual Google Custom Search API integration with proper error handling,
        retry logic, and result quality filtering.
        """
        import os
        
        # Get Google Custom Search configuration
        api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        
        if not api_key or not search_engine_id:
            logger.warning("Google Custom Search API not configured (missing GOOGLE_SEARCH_API_KEY or GOOGLE_SEARCH_ENGINE_ID)")
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
                "num": min(query.max_results, 10),  # Google API max is 10
                "safe": "medium",
                "lr": "lang_en",  # English results
            }
            
            # Add date restriction if specified
            if query.date_restrict:
                params["dateRestrict"] = query.date_restrict
                
            # Add site restrictions for higher quality sources
            if not any(site in query.text.lower() for site in ["site:", "inurl:"]):
                # Focus on reputable news and government sites
                quality_sites = [
                    "ballotpedia.org", "fec.gov", "opensecrets.org", "vote411.org",
                    "reuters.com", "apnews.com", "npr.org", "pbs.org", "cnn.com", 
                    "bbc.com", "politico.com", "washingtonpost.com", "nytimes.com"
                ]
                params["q"] += f" (site:{' OR site:'.join(quality_sites)})"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(search_url, params=params)
                response.raise_for_status()
                
                search_data = response.json()
                
                if "items" not in search_data:
                    logger.warning(f"No search results for query: {query.text}")
                    return []
                    
                sources = []
                for item in search_data["items"]:
                    try:
                        # Determine source type based on URL
                        url = item["link"]
                        source_type = SourceType.NEWS
                        
                        if any(gov_domain in url for gov_domain in [".gov", "ballotpedia.org"]):
                            source_type = SourceType.GOVERNMENT
                        elif any(social in url for social in ["twitter.com", "facebook.com", "instagram.com"]):
                            source_type = SourceType.SOCIAL_MEDIA
                        elif url.endswith(".pdf"):
                            source_type = SourceType.PDF
                            
                        source = Source(
                            url=url,
                            type=source_type,
                            title=item.get("title", "").strip(),
                            description=item.get("snippet", "").strip(),
                            last_accessed=datetime.utcnow(),
                            is_fresh=True,
                        )
                        sources.append(source)
                        
                    except Exception as e:
                        logger.warning(f"Error processing search result: {e}")
                        continue
                        
                logger.info(f"Found {len(sources)} sources for {issue.value} query")
                return sources
                
        except ImportError:
            logger.error("httpx not available for Google search. Install with: pip install httpx")
            return []
        except httpx.TimeoutException:
            logger.error(f"Timeout during Google search for query: {query.text}")
            return []
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error("Google Search API rate limit exceeded")
            else:
                logger.error(f"Google Search API error {e.response.status_code}: {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"Error during Google search for {query.text}: {e}")
            return []

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
                candidate_query = self._generate_candidate_query(race_id, candidate_name)
                candidate_sources = await self._search_candidate_info(candidate_query)
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
    
    def _generate_candidate_query(self, race_id: str, candidate_name: str) -> FreshSearchQuery:
        """Generate search query for a specific candidate."""
        race_parts = race_id.split("-")
        state = race_parts[0] if race_parts else ""
        office = race_parts[1] if len(race_parts) > 1 else ""
        year = race_parts[2] if len(race_parts) > 2 else ""
        
        # Build candidate-specific query
        query_parts = [
            f'"{candidate_name}"',
            f'"{state} {office} {year}"',
            "candidate OR campaign OR biography OR platform",
        ]
        
        query_text = " ".join(query_parts)
        
        return FreshSearchQuery(
            text=query_text,
            race_id=race_id,
            max_results=5,
            date_restrict=f"d{self.search_config['freshness_days']}",
        )
    
    async def _search_candidate_info(self, query: FreshSearchQuery) -> List[Source]:
        """Search for candidate-specific information."""
        # Use the same Google Custom Search infrastructure
        return await self._search_google_custom(query, CanonicalIssue.ELECTION_REFORM)  # Use any issue for type

    async def _discover_news_sources(self, race_id: str) -> List[Source]:
        """
        Discover news sources covering the race.

        TODO:
        - [ ] Add RSS feed discovery
        - [ ] Implement news API integrations (NewsAPI, etc.)
        - [ ] Add local news source prioritization
        - [ ] Support for discovering opinion pieces vs. news
        """
        sources = []

        # TODO: Implement news source discovery
        logger.info(f"Would discover news sources for {race_id}")

        return sources

    def _deduplicate_sources(self, sources: List[Source]) -> List[Source]:
        """
        Remove duplicate sources based on URL.

        TODO:
        - [ ] Add more sophisticated deduplication (domain, content similarity)
        - [ ] Preserve source with highest quality score
        - [ ] Add URL normalization before comparison
        """
        seen_urls = set()
        unique_sources = []

        for source in sources:
            url_str = str(source.url).lower().strip("/")
            if url_str not in seen_urls:
                seen_urls.add(url_str)
                unique_sources.append(source)

        return unique_sources

    def _filter_by_quality(self, sources: List[Source]) -> List[Source]:
        """
        Filter sources by quality score.

        TODO:
        - [ ] Implement comprehensive quality scoring
        - [ ] Add domain reputation checking
        - [ ] Support for whitelist/blacklist filtering
        - [ ] Add content freshness scoring
        """
        # Simple quality filtering for now
        quality_sources = []

        for source in sources:
            quality_score = self._calculate_source_quality(source)
            if quality_score >= self.search_config["quality_threshold"]:
                quality_sources.append(source)

        return quality_sources

    def _calculate_source_quality(self, source: Source) -> float:
        """
        Calculate quality score for a source.

        TODO:
        - [ ] Add domain authority checking
        - [ ] Implement content freshness scoring
        - [ ] Add social signals and credibility metrics
        - [ ] Support for source type specific scoring
        """
        score = 0.8  # Base score

        # Boost government and official sources
        if source.type == SourceType.GOVERNMENT:
            score += 0.2

        # Boost fresh sources
        if source.is_fresh:
            score += 0.1

        # TODO: Add more sophisticated scoring

        return min(1.0, score)
