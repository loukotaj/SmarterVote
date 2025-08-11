"""
Race Metadata Extraction Service for SmarterVote Pipeline

This service extracts high-level race details early in the pipeline to enable
more targeted discovery and search operations. It parses race IDs, performs
initial lookups for basic race information, and creates structured metadata
that can guide subsequent pipeline steps.

Key responsibilities:
- Parse race_id patterns to extract state, office, year, and race type (primary/special/runoff)
- Perform initial discovery to identify key candidates with structured information
- Determine race type (federal/state/local) and characteristics
- Generate search optimization hints for issue discovery
- Create structured RaceMetadata for pipeline use
- Implement evidence-based confidence scoring
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from ..schema import CanonicalIssue, ConfidenceLevel, FreshSearchQuery, RaceMetadata, Source, SourceType
from ..step02_discover.source_discovery_engine import SourceDiscoveryEngine
from shared.models import DiscoveredCandidate
from shared.state_constants import STATE_NAME, PRIMARY_DATE_BY_STATE
from ..providers.base import ProviderRegistry, TaskType

logger = logging.getLogger(__name__)

# Slug parsing regex pattern - matches: state-office[-district]-year[-kind]
SLUG_PATTERN = re.compile(
    r"^(?P<state>[a-z]{2})-(?P<office>[a-z-]+)"
    r"(?:-(?P<district>\d{1,2}|al))?-(?P<year>\d{4})"
    r"(?:-(?P<kind>primary|runoff|special))?$"
)


class RaceMetadataService:
    """Service for extracting structured race metadata early in pipeline."""

    def __init__(self, providers: ProviderRegistry = None):
        """Initialize the race metadata service."""
        # Initialize discovery engine for candidate and issue searches
        self.discovery_engine = SourceDiscoveryEngine()
        
        # Provider registry for AI validation
        self.providers = providers

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
            # Parse race_id components (now includes race kind)
            state, office_type, year, district, kind = self._parse_race_id(race_id)

            # Set race type flags based on slug
            is_primary = (kind == "primary")
            is_special_election = (kind == "special")
            is_runoff = (kind == "runoff")

            # Get office information
            office_info = self._get_office_info(office_type)

            # Calculate election date
            election_date = self._calculate_election_date(year)

            # Get primary date if this is a primary
            primary_date = self._get_primary_date(state, year) if is_primary else None

            # Determine jurisdiction string
            jurisdiction = self._build_jurisdiction(state, district)

            # Get major issues for this race type and state
            major_issues = self._get_major_issues(office_type, state)

            # Generate geographic search keywords
            geographic_keywords = self._generate_geographic_keywords(state, district)

            # Perform targeted search focusing on reliable sources
            logger.info(f"Performing candidate discovery search for {race_id}")
            structured_candidates = await self._discover_candidates_via_reliable_sources(
                race_id, state, office_type, year, district
            )

            # Extract incumbent party from structured candidates
            incumbent_party = self._extract_incumbent_party(structured_candidates)

            # Calculate evidence-based confidence
            confidence = self._calculate_confidence(structured_candidates, primary_date is not None)

            # Create backward-compatible string list
            discovered_candidates = [c.name for c in structured_candidates]

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
                primary_date=primary_date,
                is_special_election=is_special_election,
                is_runoff=is_runoff,
                discovered_candidates=discovered_candidates,
                structured_candidates=structured_candidates,
                incumbent_party=incumbent_party,
                major_issues=major_issues,
                geographic_keywords=geographic_keywords,
                confidence=confidence,
            )

            logger.info(
                f"✅ Extracted metadata for {race_id}: {office_info['full_name']} in {jurisdiction}, "
                f"found {len(structured_candidates)} candidates, confidence: {confidence.value}"
            )
            return metadata

        except Exception as e:
            logger.error(f"❌ Failed to extract metadata for {race_id}: {e}")
            # Return minimal metadata as fallback
            return self._create_fallback_metadata(race_id)

    def _parse_race_id(self, race_id: str) -> Tuple[str, str, int, Optional[str], Optional[str]]:
        """
        Parse race_id to extract components including race kind.

        Args:
            race_id: Race identifier like 'mo-senate-2024', 'ny-house-03-2024-primary', or 'ga-senate-2026-special'

        Returns:
            Tuple of (state, office_type, year, district, kind)
        """
        match = SLUG_PATTERN.match(race_id.lower())
        if not match:
            raise ValueError(f"Invalid race_id format: {race_id}")

        state = match.group("state").upper()
        office_type = match.group("office")
        year = int(match.group("year"))
        district = match.group("district")
        kind = match.group("kind")

        # Normalize district format
        if district and district.isdigit():
            district = district.zfill(2)  # '3' -> '03'

        # Validate state code
        if len(state) != 2 or state not in STATE_NAME:
            raise ValueError(f"Invalid state code: {state}")

        # Validate year
        if not (2020 <= year <= 2030):
            raise ValueError(f"Invalid year: {year}")

        return state, office_type, year, district, kind

    def _get_primary_date(self, state: str, year: int) -> Optional[datetime]:
        """Get primary date for state and year if available."""
        primary_dates = PRIMARY_DATE_BY_STATE.get(year, {})
        date_str = primary_dates.get(state)
        
        if date_str:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                logger.warning(f"Invalid primary date format for {state} {year}: {date_str}")
        
        return None

    def _extract_incumbent_party(self, candidates: List[DiscoveredCandidate]) -> Optional[str]:
        """Extract incumbent party from structured candidates."""
        incumbents = [c for c in candidates if c.incumbent and c.party]
        
        if not incumbents:
            return None
            
        # If multiple incumbents, prefer those from trusted sources
        for candidate in incumbents:
            if any(self._is_trusted_source(str(url)) for url in candidate.sources):
                return candidate.party
                
        # Fallback to first incumbent with party
        return incumbents[0].party

    def _calculate_confidence(self, candidates: List[DiscoveredCandidate], have_primary_date: bool) -> ConfidenceLevel:
        """Calculate evidence-based confidence score."""
        if not candidates:
            return ConfidenceLevel.LOW
            
        # Count trusted domains across all candidates
        trusted_domains = set()
        for candidate in candidates:
            for source in candidate.sources:
                if self._is_trusted_source(str(source)):
                    domain = str(source).split('/')[2]
                    trusted_domains.add(domain)
        
        trusted_domains_count = len(trusted_domains)
        
        # Apply heuristic
        if len(candidates) >= 2 and trusted_domains_count >= 2:
            confidence = ConfidenceLevel.HIGH
        elif len(candidates) >= 1 and (trusted_domains_count >= 1 or have_primary_date):
            confidence = ConfidenceLevel.MEDIUM
        else:
            confidence = ConfidenceLevel.LOW
            
        # Log reasoning for observability
        logger.info(
            f"Confidence calculation: {len(candidates)} candidates, "
            f"{trusted_domains_count} trusted domains, "
            f"primary_date: {have_primary_date} → {confidence.value}"
        )
        
        return confidence

    def _is_trusted_source(self, url: str) -> bool:
        """Check if URL is from a trusted source."""
        trusted_domains = ["fec.gov", "ballotpedia.org", "wikipedia.org"]
        return any(domain in url.lower() for domain in trusted_domains)

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
        """Generate geographic search keywords using unified state constants."""
        keywords = [state]

        # Add state name from unified mapping
        if state in STATE_NAME:
            keywords.append(STATE_NAME[state])

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
    ) -> List[DiscoveredCandidate]:
        """
        Discover candidates using reliable sources with structured information.

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

                # Extract structured candidate info from search results
                candidates_from_results = self._extract_structured_candidates_from_search_results(search_results, state, office_type)
                discovered_candidates.extend(candidates_from_results)

            # Merge and deduplicate structured candidates
            unique_candidates = self._merge_and_deduplicate_structured_candidates(discovered_candidates)

            # AI validation of candidates using provider registry
            if unique_candidates:
                logger.info(f"Validating {len(unique_candidates)} candidate(s) with AI for {race_id}")
                validated_candidates = await self._validate_structured_candidates_with_ai(
                    unique_candidates, race_id, state, office_type, year, district
                )

                logger.info(f"✅ Validated {len(validated_candidates)} candidates for {race_id}")
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
        """Generate search queries focused on Wikipedia and Ballotpedia using unified state constants."""
        queries = []

        # Get full office name and geographic terms
        office_info = self._get_office_info(office_type)
        full_office = office_info["full_name"]

        # Use unified state name mapping
        state_name = STATE_NAME.get(state, state)

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

    def _extract_structured_candidates_from_search_results(
        self, search_results: List[Source], state: str, office_type: str
    ) -> List[DiscoveredCandidate]:
        """Extract structured candidate information from search results."""
        candidates = []

        # Enhanced patterns for extracting candidate info
        candidate_patterns = [
            # Ballotpedia specific patterns with party info
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+\((?P<party>Democratic|Republican|Independent|Libertarian|Green)\)",
            r"(?:Incumbent|Senator|Representative)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\s+\((?P<party>D|R|I)\)",
            # General high-confidence patterns
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:vs\.?|versus|against)",
            r"(?:candidate|nominee)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)",
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:is running|will run|announced)",
        ]

        for source in search_results:
            # Only process results from trusted sources
            source_url = str(source.url).lower()
            if not self._is_trusted_source(source_url):
                continue

            text_to_search = f"{source.title or ''} {source.description or ''}"

            for pattern in candidate_patterns:
                matches = re.finditer(pattern, text_to_search, re.IGNORECASE)
                for match in matches:
                    name = match.group(1).strip()
                    if not self._is_valid_candidate_name(name):
                        continue

                    # Extract party information if available
                    party = None
                    if match.lastindex and match.lastindex > 1:
                        party_code = match.group(2)
                        party = self._normalize_party_name(party_code)
                    else:
                        # Try to find party info in surrounding text
                        party = self._extract_party_from_context(text_to_search, name)

                    # Check for incumbent status
                    incumbent = self._check_incumbent_status(text_to_search, name)

                    candidate = DiscoveredCandidate(
                        name=name,
                        party=party,
                        incumbent=incumbent,
                        sources=[source.url]
                    )
                    candidates.append(candidate)

        return candidates

    def _normalize_party_name(self, party_code: str) -> Optional[str]:
        """Normalize party codes and names."""
        if not party_code:
            return None
            
        party_map = {
            "D": "Democratic",
            "R": "Republican", 
            "I": "Independent",
            "L": "Libertarian",
            "G": "Green"
        }
        
        party_normalized = party_code.strip().title()
        return party_map.get(party_code.upper(), party_normalized)

    def _extract_party_from_context(self, text: str, candidate_name: str) -> Optional[str]:
        """Extract party affiliation from text context around candidate name."""
        # Look for party keywords within 80 characters of the candidate name
        name_pos = text.lower().find(candidate_name.lower())
        if name_pos == -1:
            return None
            
        context_start = max(0, name_pos - 80)
        context_end = min(len(text), name_pos + len(candidate_name) + 80)
        context = text[context_start:context_end]
        
        party_pattern = re.compile(r'\b(Democratic|Republican|Libertarian|Green|Independent)\b', re.IGNORECASE)
        match = party_pattern.search(context)
        
        return match.group(1).title() if match else None

    def _check_incumbent_status(self, text: str, candidate_name: str) -> bool:
        """Check if candidate is mentioned as incumbent."""
        # Look for incumbent keywords near the candidate name
        name_pos = text.lower().find(candidate_name.lower())
        if name_pos == -1:
            return False
            
        context_start = max(0, name_pos - 80)
        context_end = min(len(text), name_pos + len(candidate_name) + 80)
        context = text[context_start:context_end]
        
        incumbent_pattern = re.compile(r'\bincumbent\b', re.IGNORECASE)
        return bool(incumbent_pattern.search(context))

    def _merge_and_deduplicate_structured_candidates(self, candidates: List[DiscoveredCandidate]) -> List[DiscoveredCandidate]:
        """Merge and deduplicate structured candidates by name."""
        merged = {}
        
        for candidate in candidates:
            # Normalize name for deduplication
            name_key = re.sub(r'\s+', ' ', candidate.name.strip().lower())
            
            if name_key in merged:
                # Merge information from multiple sources
                existing = merged[name_key]
                
                # Prefer party info from trusted sources, or first non-None
                if not existing.party and candidate.party:
                    existing.party = candidate.party
                elif candidate.party and self._has_more_trusted_sources(candidate, existing):
                    existing.party = candidate.party
                    
                # Set incumbent if any source says so
                if candidate.incumbent:
                    existing.incumbent = True
                    
                # Merge source lists
                for source in candidate.sources:
                    if source not in existing.sources:
                        existing.sources.append(source)
            else:
                merged[name_key] = candidate
                
        return list(merged.values())[:8]  # Limit to reasonable number

    def _has_more_trusted_sources(self, candidate1: DiscoveredCandidate, candidate2: DiscoveredCandidate) -> bool:
        """Check if candidate1 has more trusted sources than candidate2."""
        trusted1 = sum(1 for url in candidate1.sources if self._is_trusted_source(str(url)))
        trusted2 = sum(1 for url in candidate2.sources if self._is_trusted_source(str(url)))
        return trusted1 > trusted2

    async def _validate_structured_candidates_with_ai(
        self, candidates: List[DiscoveredCandidate], race_id: str, state: str, office_type: str, year: int, district: Optional[str] = None
    ) -> List[DiscoveredCandidate]:
        """
        Validate structured candidates using provider registry.
        """
        if not self.providers or not candidates:
            return candidates[:5]  # Return first 5 without validation
            
        try:
            # Get models for DISCOVER task
            models = self.providers.get_enabled_models(TaskType.DISCOVER)
            if not models:
                logger.warning("No models available for candidate validation, skipping AI validation")
                return candidates[:5]
                
            # Use first available model (cheap mode will give us mini models)
            model = models[0]
            provider = self.providers.get_provider(model.provider)
            
            # Prepare context
            office_info = self._get_office_info(office_type)
            full_office = office_info["full_name"]
            district_text = f" District {district}" if district else ""

            # Create validation prompt
            candidate_names = [c.name for c in candidates]
            prompt = f"""You are validating candidates for the {year} {full_office} election in {state}{district_text}.

Here are potential candidate names found from Ballotpedia and Wikipedia searches:
{', '.join(candidate_names)}

Please analyze these names and return ONLY the candidates who are:
1. Real people (not organizations, websites, or generic terms)
2. Actually running for this specific office in {year}
3. Legitimate candidates with a reasonable chance of being on the ballot

Return your response as a simple comma-separated list of validated candidate names, or "NONE" if no valid candidates found.

Validated candidates:"""

            # Make API call through provider
            response = await provider.generate(prompt, model)
            
            if response.strip().upper() == "NONE":
                logger.info(f"AI validation found no valid candidates for {race_id}")
                return []

            # Parse validated names
            validated_names = [name.strip() for name in response.split(",") if name.strip()]
            
            # Filter original candidates to only include validated ones
            validated_candidates = []
            for candidate in candidates:
                if any(name.lower() in candidate.name.lower() or candidate.name.lower() in name.lower() 
                      for name in validated_names):
                    validated_candidates.append(candidate)
                    
            logger.info(f"AI validated {len(validated_candidates)} of {len(candidates)} candidates for {race_id}")
            return validated_candidates[:8]
            
        except Exception as e:
            logger.warning(f"Error during AI validation for {race_id}: {e}")
            return candidates[:3]  # Fallback

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
