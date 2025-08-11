"""
Race Metadata Extraction Service for SmarterVote Pipeline

This service extracts high-level race details early in the pipeline to enable
more targeted discovery and search operations. It parses race IDs, performs
initial lookups for basic race information, and creates structured metadata
that can guide subsequent pipeline steps.

Key responsibilities:
- Parse race_id patterns to extract state, office, year
- Perform initial discovery to identify key candidates
- Determine race type (federal/state/local) and characteristics
- Generate search optimization hints for issue discovery
- Create structured RaceMetadata for pipeline use
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from ..discover.source_discovery_engine import SourceDiscoveryEngine
from ..schema import CanonicalIssue, ConfidenceLevel, FreshSearchQuery, RaceMetadata, Source, SourceType

logger = logging.getLogger(__name__)


class RaceMetadataService:
    """Service for extracting structured race metadata early in pipeline."""

    def __init__(self):
        """Initialize the race metadata service."""
        # Initialize discovery engine for candidate and issue searches
        self.discovery_engine = SourceDiscoveryEngine()

        # Office type mappings
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

        # Preferred sources for candidate validation (in priority order)
        self.preferred_candidate_sources = ["ballotpedia.org", "wikipedia.org", "fec.gov", "vote411.org"]

        # Default election date patterns
        self.election_date_patterns = {
            "general": {"month": 11, "day": 5},  # First Tuesday after first Monday in November
            "primary": {"month": 3, "day": 15},  # Varies by state, using default
        }

    async def extract_race_metadata(self, race_id: str) -> RaceMetadata:
        """
        Extract comprehensive race metadata from race_id and initial discovery.

        Args:
            race_id: Race identifier like 'mo-senate-2024'

        Returns:
            RaceMetadata object with structured race information
        """
        start_time = datetime.utcnow()
        logger.info(f"📋 Starting race metadata extraction for: {race_id}")

        try:
            # Parse race_id components
            state, office_type, year, district = self._parse_race_id(race_id)
            logger.info(f"🔍 Parsed race components: {state.upper()}, {office_type}, {year}, district={district}")

            # Get office information
            office_info = self._get_office_info(office_type)
            logger.info(f"🏛️  Office: {office_info['full_name']} ({office_info['race_type']} level)")

            # Calculate election date
            election_date = self._calculate_election_date(year)

            # Determine jurisdiction string
            jurisdiction = self._build_jurisdiction(state, district)

            # Get major issues for this race type and state
            major_issues = self._get_major_issues(office_type, state)
            logger.info(f"🎯 Priority issues for {office_type}: {', '.join(major_issues[:5])}")

            # Generate geographic search keywords
            geographic_keywords = self._generate_geographic_keywords(state, district)

            # Perform targeted search focusing on reliable sources
            logger.info(f"🔍 Discovering candidates via reliable sources...")
            discovered_candidates = await self._discover_candidates_via_reliable_sources(
                race_id, state, office_type, year, district
            )

            # Create metadata object
            metadata = RaceMetadata(
                race_id=race_id,
                state=state,
                office_type=office_type,
                year=year,
                full_office_name=office_info["full_name"],
                jurisdiction=jurisdiction,
                district=district,
                election_date=election_date,
                race_type=office_info["race_type"],
                is_primary=False,  # Default, could be enhanced
                is_special_election=False,  # Default, could be enhanced
                discovered_candidates=discovered_candidates,
                major_issues=major_issues,
                geographic_keywords=geographic_keywords,
                confidence=ConfidenceLevel.HIGH,
            )

            logger.info(
                f"✅ Extracted metadata for {race_id}: {office_info['full_name']} in {jurisdiction}, found {len(discovered_candidates)} candidates"
            )
            return metadata

        except Exception as e:
            logger.error(f"❌ Failed to extract metadata for {race_id}: {e}")
            # Return minimal metadata as fallback
            return self._create_fallback_metadata(race_id)

    def _parse_race_id(self, race_id: str) -> Tuple[str, str, int, Optional[str]]:
        """
        Parse race_id to extract components.

        Args:
            race_id: Race identifier like 'mo-senate-2024' or 'ny-house-03-2024'

        Returns:
            Tuple of (state, office_type, year, district)
        """
        # Common patterns:
        # mo-senate-2024
        # ny-house-03-2024
        # ca-governor-2024
        # tx-house-15-2024

        parts = race_id.lower().split("-")

        if len(parts) < 3:
            raise ValueError(f"Invalid race_id format: {race_id}")

        state = parts[0].upper()

        # Check if there's a district number
        district = None
        if len(parts) == 4 and parts[2].isdigit():
            office_type = parts[1]
            district = parts[2].zfill(2)  # Ensure 2-digit format
            year = int(parts[3])
        else:
            office_type = parts[1]
            year = int(parts[-1])

        # Validate state code
        if len(state) != 2:
            raise ValueError(f"Invalid state code: {state}")

        # Validate year
        if not (2020 <= year <= 2030):
            raise ValueError(f"Invalid year: {year}")

        return state, office_type, year, district

    def _get_office_info(self, office_type: str) -> Dict[str, any]:
        """Get detailed office information."""
        office_info = self.office_mappings.get(office_type)
        if not office_info:
            # Default fallback
            office_info = {
                "full_name": office_type.replace("-", " ").title(),
                "race_type": "unknown",
                "term_years": 4,
                "major_issues": ["Economy", "Healthcare", "Education"],
            }
            logger.warning(f"Unknown office type '{office_type}', using fallback")

        return office_info

    def _calculate_election_date(self, year: int) -> datetime:
        """Calculate election date for given year."""
        # General election: First Tuesday after first Monday in November
        november_first = datetime(year, 11, 1)

        # Find first Monday in November
        days_to_monday = (7 - november_first.weekday()) % 7
        first_monday = november_first + timedelta(days=days_to_monday)

        # Election is first Tuesday after first Monday
        election_date = first_monday + timedelta(days=1)

        return election_date

    def _build_jurisdiction(self, state: str, district: Optional[str]) -> str:
        """Build jurisdiction string."""
        if district:
            return f"{state}-{district}"
        return state

    def _get_major_issues(self, office_type: str, state: str) -> List[str]:
        """Get major issues for this race type - only use office-based issues."""
        # Only use office-based issues, removing hardcoded state assumptions
        office_info = self._get_office_info(office_type)
        major_issues = office_info.get("major_issues", [])

        # Return only the office-specific issues without state assumptions
        return major_issues

    def _generate_geographic_keywords(self, state: str, district: Optional[str]) -> List[str]:
        """Generate geographic search keywords."""
        keywords = [state]

        # Add state name if we have a mapping
        state_names = {
            "CA": "California",
            "TX": "Texas",
            "FL": "Florida",
            "NY": "New York",
            "MO": "Missouri",
            "OH": "Ohio",
            "IL": "Illinois",
            "PA": "Pennsylvania",
            "MI": "Michigan",
            "NC": "North Carolina",
            "GA": "Georgia",
            "VA": "Virginia",
            "WA": "Washington",
            "AZ": "Arizona",
            "MA": "Massachusetts",
            "IN": "Indiana",
            "TN": "Tennessee",
            "MD": "Maryland",
            "MN": "Minnesota",
            "WI": "Wisconsin",
            "CO": "Colorado",
            "SC": "South Carolina",
            "AL": "Alabama",
            "LA": "Louisiana",
            "KY": "Kentucky",
            "OR": "Oregon",
            "OK": "Oklahoma",
            "CT": "Connecticut",
            "IA": "Iowa",
            "MS": "Mississippi",
            "AR": "Arkansas",
            "KS": "Kansas",
            "UT": "Utah",
            "NV": "Nevada",
            "NM": "New Mexico",
            "WV": "West Virginia",
            "NE": "Nebraska",
            "ID": "Idaho",
            "HI": "Hawaii",
            "NH": "New Hampshire",
            "ME": "Maine",
            "RI": "Rhode Island",
            "MT": "Montana",
            "DE": "Delaware",
            "SD": "South Dakota",
            "ND": "North Dakota",
            "AK": "Alaska",
            "VT": "Vermont",
            "WY": "Wyoming",
            "DC": "Washington DC",
        }

        if state in state_names:
            keywords.append(state_names[state])

        # Add district if applicable
        if district:
            keywords.extend([f"District {district}", f"CD-{district}", f"{state}-{district}"])

        return keywords

    def _create_fallback_metadata(self, race_id: str) -> RaceMetadata:
        """Create minimal fallback metadata when parsing fails."""
        return RaceMetadata(
            race_id=race_id,
            state="XX",
            office_type="unknown",
            year=2024,
            full_office_name="Unknown Office",
            jurisdiction="Unknown",
            election_date=datetime(2024, 11, 5),
            race_type="unknown",
            discovered_candidates=[],
            major_issues=["Economy", "Healthcare"],
            geographic_keywords=[],
            confidence=ConfidenceLevel.LOW,
        )

    async def _discover_candidates_via_reliable_sources(
        self, race_id: str, state: str, office_type: str, year: int, district: Optional[str] = None
    ) -> List[str]:
        """
        Discover candidates using reliable sources with AI validation.

        Focuses on Wikipedia and Ballotpedia for high-quality candidate data.
        """
        discovered_candidates = []

        try:
            # Create targeted searches for reliable sources only
            search_queries = self._generate_reliable_source_queries(race_id, state, office_type, year, district)

            for query in search_queries:
                logger.debug(f"Searching reliable sources with query: {query.text}")

                # Use discovery engine to search for candidate information
                search_results = await self.discovery_engine._search_google_custom(query, CanonicalIssue.ELECTION_REFORM)

                # Extract candidate names from search results
                candidates_from_results = self._extract_candidates_from_search_results(search_results, state, office_type)
                discovered_candidates.extend(candidates_from_results)

            # Deduplicate candidates
            unique_candidates = self._clean_and_deduplicate_candidates(discovered_candidates)

            # AI validation of candidates using GPT-4o-mini
            if unique_candidates:
                logger.info(f"Validating {len(unique_candidates)} candidate(s) with AI for {race_id}")
                validated_candidates = await self._validate_candidates_with_ai(
                    unique_candidates, race_id, state, office_type, year, district
                )

                logger.info(f"✅ Validated {len(validated_candidates)} candidates for {race_id}: {validated_candidates}")
                return validated_candidates
            else:
                logger.warning(f"No candidates found in reliable sources for {race_id}")
                return []

        except Exception as e:
            logger.warning(f"Error during candidate discovery for {race_id}: {e}")
            return []

    def _generate_reliable_source_queries(
        self, race_id: str, state: str, office_type: str, year: int, district: Optional[str] = None
    ) -> List[FreshSearchQuery]:
        """Generate search queries focused on Wikipedia and Ballotpedia."""
        queries = []

        # Get full office name and geographic terms
        office_info = self._get_office_info(office_type)
        full_office = office_info["full_name"]

        # Add state name if available
        state_names = {
            "CA": "California",
            "TX": "Texas",
            "FL": "Florida",
            "NY": "New York",
            "MO": "Missouri",
            "OH": "Ohio",
            "IL": "Illinois",
            "PA": "Pennsylvania",
            "MI": "Michigan",
            "NC": "North Carolina",
            "GA": "Georgia",
            "VA": "Virginia",
            "WA": "Washington",
            "AZ": "Arizona",
            "MA": "Massachusetts",
            "IN": "Indiana",
            "TN": "Tennessee",
            "MD": "Maryland",
            "MN": "Minnesota",
            "WI": "Wisconsin",
            "CO": "Colorado",
            "SC": "South Carolina",
            "AL": "Alabama",
            "LA": "Louisiana",
            "KY": "Kentucky",
            "OR": "Oregon",
            "OK": "Oklahoma",
            "CT": "Connecticut",
            "IA": "Iowa",
            "MS": "Mississippi",
            "AR": "Arkansas",
            "KS": "Kansas",
            "UT": "Utah",
            "NV": "Nevada",
            "NM": "New Mexico",
            "WV": "West Virginia",
            "NE": "Nebraska",
            "ID": "Idaho",
            "HI": "Hawaii",
            "NH": "New Hampshire",
            "ME": "Maine",
            "RI": "Rhode Island",
            "MT": "Montana",
            "DE": "Delaware",
            "SD": "South Dakota",
            "ND": "North Dakota",
            "AK": "Alaska",
            "VT": "Vermont",
            "WY": "Wyoming",
            "DC": "Washington DC",
        }
        state_name = state_names.get(state, state)

        # District information
        district_text = f" district {district}" if district else ""

        # Ballotpedia searches (highest priority)
        ballotpedia_terms = [
            f"site:ballotpedia.org {year} {state_name}{district_text} {office_type} election",
            f"site:ballotpedia.org {state_name} {full_office} {year} candidates",
            f"site:ballotpedia.org {year} {state} {office_type} general election",
        ]

        # Wikipedia searches
        wikipedia_terms = [
            f"site:wikipedia.org {year} {state_name}{district_text} {office_type} election",
            f"site:wikipedia.org {year} United States {office_type} elections {state_name}",
        ]

        # FEC searches for federal races
        fec_terms = []
        if office_type in ["senate", "house"]:
            fec_terms = [f"site:fec.gov {year} {state} {office_type} candidates"]

        all_terms = ballotpedia_terms + wikipedia_terms + fec_terms

        # Create search queries
        for term in all_terms:
            queries.append(FreshSearchQuery(race_id=race_id, text=term, max_results=10, date_restrict="y1"))  # Last year

        return queries

    async def _validate_candidates_with_ai(
        self, candidate_names: List[str], race_id: str, state: str, office_type: str, year: int, district: Optional[str] = None
    ) -> List[str]:
        """
        Validate candidates using GPT-4o-mini to ensure accuracy.

        This AI call helps filter out false positives and confirms real candidates.
        """
        try:
            import os

            import openai

            # Get OpenAI API key
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OpenAI API key not found, skipping AI validation")
                return candidate_names[:5]  # Return first 5 without validation

            # Initialize OpenAI client
            client = openai.OpenAI(api_key=api_key)

            # Prepare context
            office_info = self._get_office_info(office_type)
            full_office = office_info["full_name"]
            district_text = f" District {district}" if district else ""

            # Create validation prompt
            prompt = f"""You are validating candidates for the {year} {full_office} election in {state}{district_text}.

Here are potential candidate names found from Ballotpedia and Wikipedia searches:
{', '.join(candidate_names)}

Please analyze these names and return ONLY the candidates who are:
1. Real people (not organizations, websites, or generic terms)
2. Actually running for this specific office in {year}
3. Legitimate candidates with a reasonable chance of being on the ballot

Return your response as a simple comma-separated list of validated candidate names, or "NONE" if no valid candidates found.

Examples of what to EXCLUDE:
- Generic terms like "Republican candidate", "Democratic challenger"
- Website names, organization names
- Candidates running for different offices
- Candidates from different years
- Obviously fake or malformed names

Examples of what to INCLUDE:
- Full names of real people running for this office
- Incumbents seeking re-election
- Serious challengers from major or minor parties

Validated candidates:"""

            # Make API call to GPT-4o-mini
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise fact-checker for electoral data. Only validate candidates you are confident are real people running for the specified office.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=200,
                temperature=0.1,  # Low temperature for consistency
            )

            # Parse response
            validation_result = response.choices[0].message.content.strip()

            if validation_result.upper() == "NONE":
                logger.info(f"AI validation found no valid candidates for {race_id}")
                return []

            # Parse validated candidates
            validated_candidates = [
                name.strip() for name in validation_result.split(",") if name.strip() and len(name.strip()) > 3
            ]

            # Limit to reasonable number
            validated_candidates = validated_candidates[:8]

            logger.info(f"AI validated {len(validated_candidates)} of {len(candidate_names)} candidates for {race_id}")
            return validated_candidates

        except Exception as e:
            logger.warning(f"Error during AI validation for {race_id}: {e}")
            # Return first few candidates as fallback
            return candidate_names[:3]

    def _extract_candidates_from_search_results(self, search_results: List[Source], state: str, office_type: str) -> List[str]:
        """Extract candidate names from search result titles and descriptions from reliable sources."""
        candidates = []

        # Enhanced patterns for Wikipedia and Ballotpedia
        candidate_patterns = [
            # Ballotpedia specific patterns
            r"(?:General election|Primary election).*?([A-Z][a-z]+\s+[A-Z][a-z]+)(?:\s+\([DR]\))?",
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:won|defeated|advanced)",
            r"Candidates:\s*([A-Z][a-z]+\s+[A-Z][a-z]+)",
            # Wikipedia specific patterns
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+\((?:Democratic|Republican|Independent)",
            r"(?:Incumbent|Senator|Representative)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)",
            # General high-confidence patterns
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:vs\.?|versus|against)",
            r"(?:candidate|nominee)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)",
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:is running|will run|announced)",
        ]

        for source in search_results:
            # Only process results from our preferred sources
            source_url = str(source.url).lower()
            if not any(preferred in source_url for preferred in self.preferred_candidate_sources):
                continue

            text_to_search = f"{source.title or ''} {source.description or ''}"

            for pattern in candidate_patterns:
                matches = re.findall(pattern, text_to_search, re.IGNORECASE)
                for match in matches:
                    # Clean up the name
                    candidate_name = match.strip()
                    if self._is_valid_candidate_name(candidate_name):
                        candidates.append(candidate_name)

        return candidates

    def _is_valid_candidate_name(self, name: str) -> bool:
        """Validate if a string looks like a real candidate name - more strict validation."""
        if not name or len(name) < 5:
            return False

        # Expanded list of false positives to exclude
        false_positives = [
            "election",
            "vote",
            "ballot",
            "primary",
            "general",
            "race",
            "campaign",
            "candidate",
            "running",
            "office",
            "district",
            "state",
            "federal",
            "republican",
            "democrat",
            "party",
            "politics",
            "voter",
            "poll",
            "winner",
            "incumbent",
            "challenger",
            "nominee",
            "results",
            "ballotpedia",
            "wikipedia",
            "search",
            "page",
            "article",
            "category",
            "portal",
            "template",
            "election results",
            "voting",
            "elections",
            "candidates",
            "political",
            "government",
            "congress",
            "senate race",
            "house race",
            "governor race",
            "united states",
            "general election",
        ]

        name_lower = name.lower()
        if any(fp in name_lower for fp in false_positives):
            return False

        # Must have at least two words (first and last name)
        parts = name.split()
        if len(parts) < 2:
            return False

        # Each part should be a proper name (starts with capital)
        if not all(part[0].isupper() and part[1:].islower() for part in parts if part and len(part) > 1):
            return False

        # Exclude names that are too long (likely false positives)
        if len(parts) > 4:
            return False

        # Exclude single letter "names"
        if any(len(part) < 2 for part in parts):
            return False

        return True

    def _clean_and_deduplicate_candidates(self, candidates: List[str]) -> List[str]:
        """Clean and deduplicate candidate names."""
        cleaned = []
        seen_names = set()

        for candidate in candidates:
            # Clean the name
            clean_name = re.sub(r"\s+", " ", candidate.strip())
            clean_name = re.sub(r"[^\w\s\-\.]", "", clean_name)

            # Normalize for deduplication
            name_key = clean_name.lower().replace(".", "").replace("-", " ")

            if name_key not in seen_names and len(clean_name) > 3:
                seen_names.add(name_key)
                cleaned.append(clean_name)

        # Limit to reasonable number of candidates
        return cleaned[:8]  # Reduced limit for higher quality
