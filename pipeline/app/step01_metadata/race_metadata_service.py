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

from ..schema import CanonicalIssue, ConfidenceLevel, DiscoveredCandidate, FreshSearchQuery, RaceMetadata, Source, SourceType
from ..step02_discover.source_discovery_engine import SourceDiscoveryEngine

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
        logger.info(f"Extracting race metadata for: {race_id}")

        try:
            # Parse race_id components with extended support
            state, office_type, year, district, is_primary, is_special, is_runoff = self._parse_race_id(race_id)

            # Get office information
            office_info = self._get_office_info(office_type)

            # Calculate election date
            election_date = self._calculate_election_date(year)

            # Determine jurisdiction string
            jurisdiction = self._build_jurisdiction(state, district)

            # Get major issues for this race type and state
            major_issues = self._get_major_issues(office_type, state)

            # Generate geographic search keywords
            geographic_keywords = self._generate_geographic_keywords(state, district)

            # Perform targeted search focusing on reliable sources
            logger.info(f"Performing candidate discovery search for {race_id}")
            discovered_candidates, discovered_candidate_details = await self._discover_candidates_via_reliable_sources(
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
                is_primary=is_primary,
                is_special_election=is_special,
                is_runoff=is_runoff,
                discovered_candidates=discovered_candidates,
                discovered_candidate_details=discovered_candidate_details,
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

    def _parse_race_id(self, race_id: str) -> Tuple[str, str, int, Optional[str], bool, bool, bool]:
        """
        Parse race_id to extract components including race type indicators.

        Args:
            race_id: Race identifier like 'mo-senate-2024', 'ga-senate-2026-primary', 
                    'ny-house-03-2025-special', or 'tx-railroad-commissioner-2026-runoff'

        Returns:
            Tuple of (state, office_type, year, district, is_primary, is_special, is_runoff)
        """
        # Extended patterns:
        # mo-senate-2024
        # ny-house-03-2024
        # ca-governor-2024
        # ga-senate-2026-primary
        # ny-house-03-2025-special
        # tx-railroad-commissioner-2026-runoff

        # Use regex to parse complex patterns
        slug_pattern = re.compile(
            r"^(?P<state>[a-z]{2})-(?P<office>[\w-]+?)(?:-(?P<district>\d{1,2}))?-(?P<year>\d{4})(?:-(?P<type>primary|special|runoff))?$",
            re.IGNORECASE
        )
        
        match = slug_pattern.match(race_id.lower())
        if not match:
            raise ValueError(f"Invalid race_id format: {race_id}")

        state = match.group('state').upper()
        office_type = match.group('office')
        year = int(match.group('year'))
        district = match.group('district')
        race_type_suffix = match.group('type')
        
        # Format district as 2-digit if present
        if district:
            district = district.zfill(2)

        # Determine race type flags
        is_primary = race_type_suffix == 'primary'
        is_special = race_type_suffix == 'special'
        is_runoff = race_type_suffix == 'runoff'

        # Validate state code
        if len(state) != 2:
            raise ValueError(f"Invalid state code: {state}")

        # Validate year
        if not (2020 <= year <= 2030):
            raise ValueError(f"Invalid year: {year}")

        return state, office_type, year, district, is_primary, is_special, is_runoff

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
    ) -> Tuple[List[str], List[DiscoveredCandidate]]:
        """
        Discover candidates using reliable sources with AI validation.

        Focuses on Wikipedia and Ballotpedia for high-quality candidate data.
        
        Returns:
            Tuple of (candidate_names_list, structured_candidate_list)
        """
        discovered_candidate_details = []

        try:
            # Create targeted searches for reliable sources only
            search_queries = self._generate_reliable_source_queries(race_id, state, office_type, year, district)

            for query in search_queries:
                logger.debug(f"Searching reliable sources with query: {query.text}")

                # Use discovery engine to search for candidate information
                search_results = await self.discovery_engine._search_google_custom(query, CanonicalIssue.ELECTION_REFORM)

                # Extract structured candidate data from search results
                candidates_from_results = self._extract_candidates_from_search_results(search_results, state, office_type)
                discovered_candidate_details.extend(candidates_from_results)

            # Deduplicate candidates
            unique_candidate_details = self._clean_and_deduplicate_structured_candidates(discovered_candidate_details)

            # AI validation of candidates using GPT-4o-mini
            if unique_candidate_details:
                logger.info(f"Validating {len(unique_candidate_details)} candidate(s) with AI for {race_id}")
                validated_candidate_details = await self._validate_structured_candidates_with_ai(
                    unique_candidate_details, race_id, state, office_type, year, district
                )

                # Extract simple names for backward compatibility
                validated_candidate_names = [candidate.name for candidate in validated_candidate_details]

                logger.info(f"✅ Validated {len(validated_candidate_details)} candidates for {race_id}: {validated_candidate_names}")
                return validated_candidate_names, validated_candidate_details
            else:
                logger.warning(f"No candidates found in reliable sources for {race_id}")
                return [], []

        except Exception as e:
            logger.warning(f"Error during candidate discovery for {race_id}: {e}")
            return [], []

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

    def _extract_candidates_from_search_results(self, search_results: List[Source], state: str, office_type: str) -> List[DiscoveredCandidate]:
        """Extract structured candidate data from search result titles and descriptions from reliable sources."""
        candidates = []

        # Enhanced patterns for Wikipedia and Ballotpedia with party and incumbent capture
        candidate_patterns = [
            # Ballotpedia specific patterns with party and incumbent
            r"(?:General election|Primary election).*?([A-Z][a-z]+\s+[A-Z][a-z]+)(?:\s+\(([DR]|Democratic|Republican|Independent)\))?(?:\s+\((?:Incumbent|Inc\.)\))?",
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:won|defeated|advanced).*?(?:\(([DR]|Democratic|Republican|Independent)\))?",
            r"Candidates:\s*([A-Z][a-z]+\s+[A-Z][a-z]+)(?:\s+\(([DR]|Democratic|Republican|Independent)\))?",
            # Wikipedia specific patterns with party and incumbent
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+\((Democratic|Republican|Independent)(?:,\s+(?:incumbent|Incumbent))?\)",
            r"(?:Incumbent|Senator|Representative)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)(?:\s+\((Democratic|Republican|Independent)\))?",
            # General high-confidence patterns
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:vs\.?|versus|against).*?(?:\(([DR]|Democratic|Republican|Independent)\))?",
            r"(?:candidate|nominee)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)(?:\s+\((Democratic|Republican|Independent)\))?",
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:is running|will run|announced).*?(?:\(([DR]|Democratic|Republican|Independent)\))?",
        ]

        # Enhanced patterns specifically for incumbent detection
        incumbent_patterns = [
            r"(?:incumbent|Incumbent)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)",
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)(?:\s+\(.*?(?:incumbent|Incumbent).*?\))",
            r"([A-Z][a-z]+\s+[A-Z][a-z]+).*?(?:incumbent|Incumbent)",
        ]

        for source in search_results:
            # Only process results from our preferred sources
            source_url = str(source.url).lower()
            if not any(preferred in source_url for preferred in self.preferred_candidate_sources):
                continue

            text_to_search = f"{source.title or ''} {source.description or ''}"

            # Extract candidates with party information
            for pattern in candidate_patterns:
                matches = re.findall(pattern, text_to_search, re.IGNORECASE)
                for match in matches:
                    # Handle different match structures
                    if isinstance(match, tuple):
                        candidate_name = match[0].strip() if match[0] else ""
                        party_info = match[1].strip() if len(match) > 1 and match[1] else None
                    else:
                        candidate_name = match.strip()
                        party_info = None

                    if self._is_valid_candidate_name(candidate_name):
                        # Normalize party information
                        normalized_party = self._normalize_party_info(party_info)
                        
                        # Check if this candidate is marked as incumbent
                        is_incumbent = self._check_incumbent_status(candidate_name, text_to_search)

                        discovered_candidate = DiscoveredCandidate(
                            name=candidate_name,
                            party=normalized_party,
                            incumbent=is_incumbent,
                            sources=[source.url]
                        )
                        candidates.append(discovered_candidate)

            # Also check for incumbents separately
            for pattern in incumbent_patterns:
                matches = re.findall(pattern, text_to_search, re.IGNORECASE)
                for match in matches:
                    candidate_name = match.strip() if isinstance(match, str) else match[0].strip()
                    if self._is_valid_candidate_name(candidate_name):
                        # Check if we already have this candidate
                        existing_candidate = next((c for c in candidates if c.name.lower() == candidate_name.lower()), None)
                        if existing_candidate:
                            existing_candidate.incumbent = True
                        else:
                            discovered_candidate = DiscoveredCandidate(
                                name=candidate_name,
                                party=None,
                                incumbent=True,
                                sources=[source.url]
                            )
                            candidates.append(discovered_candidate)

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

    def _normalize_party_info(self, party_info: Optional[str]) -> Optional[str]:
        """Normalize party information to standard format."""
        if not party_info:
            return None
        
        party_lower = party_info.lower().strip()
        
        # Map common abbreviations and variations to standard names
        party_mappings = {
            'd': 'Democratic',
            'r': 'Republican', 
            'i': 'Independent',
            'dem': 'Democratic',
            'rep': 'Republican',
            'gop': 'Republican',
            'ind': 'Independent',
            'democratic': 'Democratic',
            'republican': 'Republican',
            'independent': 'Independent'
        }
        
        return party_mappings.get(party_lower, party_info.title())

    def _check_incumbent_status(self, candidate_name: str, text: str) -> bool:
        """Check if candidate is marked as incumbent in the text."""
        # Look for incumbent markers near the candidate name
        name_lower = candidate_name.lower()
        text_lower = text.lower()
        
        # Simple proximity check - if "incumbent" appears within 50 characters of the name
        name_pos = text_lower.find(name_lower)
        if name_pos == -1:
            return False
            
        # Check text around the candidate name for incumbent markers
        start = max(0, name_pos - 50)
        end = min(len(text_lower), name_pos + len(name_lower) + 50)
        surrounding_text = text_lower[start:end]
        
        incumbent_markers = ['incumbent', 'inc.', '(inc)', 'sitting']
        return any(marker in surrounding_text for marker in incumbent_markers)

    def _clean_and_deduplicate_structured_candidates(self, candidates: List[DiscoveredCandidate]) -> List[DiscoveredCandidate]:
        """Clean and deduplicate structured candidate data."""
        cleaned = []
        seen_names = set()

        for candidate in candidates:
            # Clean the name
            clean_name = re.sub(r"\s+", " ", candidate.name.strip())
            clean_name = re.sub(r"[^\w\s\-\.]", "", clean_name)

            # Normalize for deduplication
            name_key = clean_name.lower().replace(".", "").replace("-", " ")

            if name_key not in seen_names and len(clean_name) > 3:
                # Update the candidate with clean name
                candidate.name = clean_name
                
                # If we've seen this candidate before, merge the data
                existing = next((c for c in cleaned if c.name.lower().replace(".", "").replace("-", " ") == name_key), None)
                if existing:
                    # Merge sources
                    existing.sources.extend(candidate.sources)
                    # Update party info if missing
                    if not existing.party and candidate.party:
                        existing.party = candidate.party
                    # Update incumbent status
                    if candidate.incumbent:
                        existing.incumbent = True
                else:
                    seen_names.add(name_key)
                    cleaned.append(candidate)

        # Limit to reasonable number of candidates
        return cleaned[:8]  # Reduced limit for higher quality

    async def _validate_structured_candidates_with_ai(
        self, candidate_details: List[DiscoveredCandidate], race_id: str, state: str, office_type: str, year: int, district: Optional[str] = None
    ) -> List[DiscoveredCandidate]:
        """
        Validate structured candidates using GPT-4o-mini to ensure accuracy.

        This AI call helps filter out false positives and confirms real candidates.
        """
        try:
            import os

            import openai

            # Get OpenAI API key
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OpenAI API key not found, skipping AI validation")
                return candidate_details[:5]  # Return first 5 without validation

            # Initialize OpenAI client
            client = openai.OpenAI(api_key=api_key)

            # Prepare context
            office_info = self._get_office_info(office_type)
            full_office = office_info["full_name"]
            district_text = f" District {district}" if district else ""

            # Format candidate list for validation
            candidate_list = []
            for candidate in candidate_details:
                party_str = f" ({candidate.party})" if candidate.party else ""
                incumbent_str = " (Incumbent)" if candidate.incumbent else ""
                candidate_list.append(f"{candidate.name}{party_str}{incumbent_str}")

            # Create validation prompt
            prompt = f"""You are validating candidates for the {year} {full_office} election in {state}{district_text}.

Here are potential candidates found from Ballotpedia and Wikipedia searches:
{chr(10).join(candidate_list)}

Please analyze these candidates and return ONLY the valid ones as a JSON array. Each candidate should be an object with:
- "name": full name of the candidate
- "party": party affiliation (Democratic, Republican, Independent, or null)
- "incumbent": boolean indicating if they are the incumbent

Only include candidates who are:
1. Real people running for this specific office in {year}
2. Actually legitimate candidates with a reasonable chance of being on the ballot
3. Not organizations, websites, or generic terms

Return your response as a JSON array only, no other text.

Example format:
[
  {{"name": "John Smith", "party": "Democratic", "incumbent": true}},
  {{"name": "Jane Doe", "party": "Republican", "incumbent": false}}
]

Validated candidates JSON:"""

            # Make API call to GPT-4o-mini
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise fact-checker for electoral data. Only validate candidates you are confident are real people running for the specified office. Return only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.1,  # Low temperature for consistency
            )

            # Parse response
            import json
            validation_result = response.choices[0].message.content.strip()

            try:
                validated_data = json.loads(validation_result)
                validated_candidates = []
                
                for item in validated_data:
                    if isinstance(item, dict) and "name" in item:
                        validated_candidates.append(DiscoveredCandidate(
                            name=item["name"],
                            party=item.get("party"),
                            incumbent=item.get("incumbent", False),
                            sources=[source for candidate in candidate_details 
                                   if candidate.name.lower() == item["name"].lower() 
                                   for source in candidate.sources][:1]  # Take first source
                        ))

                logger.info(f"AI validated {len(validated_candidates)} of {len(candidate_details)} candidates for {race_id}")
                return validated_candidates[:8]

            except json.JSONDecodeError:
                logger.warning(f"Failed to parse AI validation response as JSON for {race_id}")
                return candidate_details[:3]  # Return first few as fallback

        except Exception as e:
            logger.warning(f"Error during AI validation for {race_id}: {e}")
            # Return first few candidates as fallback
            return candidate_details[:3]

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
