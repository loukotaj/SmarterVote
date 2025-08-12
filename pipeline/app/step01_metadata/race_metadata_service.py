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
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from shared.models import DiscoveredCandidate
from shared.state_constants import PRIMARY_DATE_BY_STATE, STATE_NAME

from ..providers.base import ProviderRegistry, TaskType
from ..schema import CanonicalIssue, ConfidenceLevel, FreshSearchQuery, RaceMetadata, Source, SourceType
from ..step02_discover.source_discovery_engine import SourceDiscoveryEngine

logger = logging.getLogger(__name__)

# Trusted domains for candidate validation and confidence scoring
TRUSTED_DOMAINS = {"ballotpedia.org", "wikipedia.org", "fec.gov", "vote411.org"}

# Slug parsing regex pattern - matches: state-office[-district]-year[-kind]
# Uses non-greedy matching for office to properly handle at-large districts
SLUG_PATTERN = re.compile(
    r"^(?P<state>[a-z]{2})-(?P<office>[a-z]+(?:-[a-z]+)*?)"
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
            is_primary = kind == "primary"
            is_special_election = kind == "special"
            is_runoff = kind == "runoff"

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

        # Normalize district format - handle "al" -> "AL" for at-large
        if district:
            if district.lower() == "al":
                district = "AL"
            elif district.isdigit():
                district = district.zfill(2)  # '3' -> '03'

        # Validate state code
        if len(state) != 2 or state not in STATE_NAME:
            raise ValueError(f"Invalid state code: {state}")

        # Validate year - allow current year ±2
        current_year = datetime.utcnow().year
        min_year = current_year - 2
        max_year = current_year + 2
        if not (min_year <= year <= max_year):
            raise ValueError(f"Invalid year: {year} (must be between {min_year} and {max_year})")

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
        """Calculate evidence-based confidence score using normalized domain matching."""
        if not candidates:
            return ConfidenceLevel.LOW

        # Count unique trusted domains across all candidates using normalized extraction
        trusted_domains = set()
        has_gov_source = False
        
        for candidate in candidates:
            for source in candidate.sources:
                source_str = str(source).lower().strip()
                if self._is_trusted_source(source_str):
                    try:
                        parsed_url = urlparse(source_str)
                        domain = parsed_url.netloc.removeprefix('www.').strip()
                        trusted_domains.add(domain)
                        
                        # Check for .gov sources
                        if domain.endswith('.gov'):
                            has_gov_source = True
                    except Exception:
                        # Fallback to simpler domain extraction
                        domain_parts = source_str.split("/")
                        if len(domain_parts) > 2:
                            domain = domain_parts[2].removeprefix('www.').strip()
                            trusted_domains.add(domain)
                            if domain.endswith('.gov'):
                                has_gov_source = True

        trusted_domains_count = len(trusted_domains)

        # Enhanced heuristic: consider both candidate count and domain diversity
        # Heuristic bump for .gov sources + trusted source combination
        if has_gov_source and trusted_domains_count >= 1:
            confidence = ConfidenceLevel.HIGH
        elif len(candidates) >= 2 and trusted_domains_count >= 2:
            confidence = ConfidenceLevel.HIGH
        elif len(candidates) >= 1 and (trusted_domains_count >= 1 or have_primary_date):
            confidence = ConfidenceLevel.MEDIUM
        else:
            confidence = ConfidenceLevel.LOW

        # Log reasoning for observability
        logger.info(
            f"Confidence calculation: {len(candidates)} candidates, "
            f"{trusted_domains_count} trusted domains ({', '.join(trusted_domains)}), "
            f"has_gov: {has_gov_source}, primary_date: {have_primary_date} → {confidence.value}"
        )

        return confidence

    def _is_trusted_source(self, url: str) -> bool:
        """Check if URL is from a trusted source using proper domain boundary checks."""
        try:
            host = urlparse(url.lower()).netloc.removeprefix("www.")
            return any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS)
        except Exception:
            return False

    def _get_office_info(self, office_type: str) -> Dict[str, Any]:
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
            if district == "AL":
                return f"{state}-AL"  # At-large district
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

        # Add district-specific keywords
        if district:
            if district == "AL":
                # At-large district keywords
                keywords.extend(["At-Large", "CD-AL", f"{state}-AL", "at-large"])
            else:
                # Numbered district keywords
                keywords.extend([f"District {district}", f"CD-{district}", f"{state}-{district}"])

        return keywords

    def _create_fallback_metadata(self, race_id: str) -> RaceMetadata:
        """Create minimal fallback metadata when parsing fails."""
        current_year = datetime.utcnow().year
        fallback_election_date = self._calculate_election_date(current_year)
        
        return RaceMetadata(
            race_id=race_id,
            state="XX",
            office_type="unknown",
            year=current_year,
            full_office_name="Unknown Office",
            jurisdiction="Unknown",
            election_date=fallback_election_date,
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

                # Use discovery engine's public search method
                search_results = await self.discovery_engine.search(query, CanonicalIssue.ELECTION_REFORM)

                # Extract structured candidate info from search results
                candidates_from_results = self._extract_structured_candidates_from_search_results(
                    search_results, state, office_type
                )
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

        # Enhanced district handling
        district_text = ""
        district_keywords = []
        if district:
            if district == "AL":
                district_text = " at-large"
                district_keywords = ["at-large", "At-Large", "CD-AL"]
            else:
                district_text = f" district {district}"
                district_keywords = [f"district {district}", f"District {district}", f"CD-{district}"]

        # Ballotpedia searches (highest priority) - include both full office and district terms
        ballotpedia_terms = [
            f"site:ballotpedia.org {year} {state_name}{district_text} {office_type} election",
            f"site:ballotpedia.org {state_name} {full_office} {year} candidates",
            f"site:ballotpedia.org {year} {state} {office_type} general election",
        ]

        # Add district-specific Ballotpedia queries
        if district_keywords:
            for keyword in district_keywords:
                ballotpedia_terms.append(f"site:ballotpedia.org {state_name} {full_office} {year} {keyword}")

        # Wikipedia searches - include both full office and district terms
        wikipedia_terms = [
            f"site:wikipedia.org {year} {state_name}{district_text} {office_type} election",
            f"site:wikipedia.org {year} United States {office_type} elections {state_name}",
        ]

        # Add district-specific Wikipedia queries
        if district_keywords:
            for keyword in district_keywords:
                wikipedia_terms.append(f"site:wikipedia.org {year} {state_name} {office_type} {keyword}")

        # FEC searches for federal races - include district terms
        fec_terms = []
        if office_type in ["senate", "house"]:
            fec_terms = [f"site:fec.gov {year} {state} {office_type} candidates"]
            if district_keywords:
                for keyword in district_keywords:
                    fec_terms.append(f"site:fec.gov {year} {state} {office_type} {keyword}")

        all_terms = ballotpedia_terms + wikipedia_terms + fec_terms

        # Create search queries with relaxed date restrictions
        for term in all_terms:
            # Relax date restriction - allow y2 (2 years) for better coverage of upcoming races
            queries.append(FreshSearchQuery(race_id=race_id, text=term, max_results=10, date_restrict="y2"))

        return queries

    def _extract_structured_candidates_from_search_results(
        self, search_results: List[Source], state: str, office_type: str
    ) -> List[DiscoveredCandidate]:
        """Extract structured candidate information from search results."""
        candidates = []

        # Enhanced patterns for extracting candidate info with better name and party support
        candidate_patterns = [
            # Ballotpedia specific patterns with comprehensive party info
            r"([A-Z][a-z]+(?:\s+[A-Z]\.?\s+)?[A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+\((?P<party>Democratic|Republican|Independent|Libertarian|Green|Nonpartisan|Unaffiliated|NPP)\)",
            r"(?:Incumbent|Senator|Representative)\s+([A-Z][a-z]+(?:\s+[A-Z]\.?\s+)?[A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+\((?P<party>D|R|I|L|G|NP|U)\)",
            # General high-confidence patterns with middle initials and hyphens
            r"([A-Z][a-z]+(?:\s+[A-Z]\.?\s+)?[A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+(?:vs\.?|versus|against)",
            r"(?:candidate|nominee)\s+([A-Z][a-z]+(?:\s+[A-Z]\.?\s+)?[A-Z][a-z]+(?:-[A-Z][a-z]+)?)",
            r"([A-Z][a-z]+(?:\s+[A-Z]\.?\s+)?[A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+(?:is running|will run|announced)",
            # Three-name patterns (First Middle Last)
            r"([A-Z][a-z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+\((?P<party>D|R|I|L|G|Democratic|Republican|Independent|Libertarian|Green|Nonpartisan|Unaffiliated|NPP)\)",
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

                    # Check for incumbent status with enhanced context matching
                    incumbent = self._check_incumbent_status(text_to_search, name)

                    # Normalize candidate source URLs
                    normalized_source = self._normalize_source_url(source.url)
                    candidate = DiscoveredCandidate(name=name, party=party, incumbent=incumbent, sources=[normalized_source])
                    candidates.append(candidate)

        return candidates

    def _normalize_party_name(self, party_code: str) -> Optional[str]:
        """Normalize party codes and names including aliases."""
        if not party_code:
            return None

        party_map = {
            "D": "Democratic", 
            "R": "Republican", 
            "I": "Independent", 
            "L": "Libertarian", 
            "G": "Green",
            "NP": "Nonpartisan",
            "U": "Unaffiliated",
            "NPP": "No Party Preference"
        }

        party_code_upper = party_code.strip().upper()
        if party_code_upper in party_map:
            return party_map[party_code_upper]
        
        # Handle full names
        party_normalized = party_code.strip().title()
        return party_normalized

    def _normalize_source_url(self, url) -> str:
        """Normalize source URL to lowercase for consistent deduplication."""
        return str(url).lower().strip()

    def _extract_party_from_context(self, text: str, candidate_name: str) -> Optional[str]:
        """Extract party affiliation from text context around candidate name."""
        # Look for party keywords within 80 characters of the candidate name
        name_pos = text.lower().find(candidate_name.lower())
        if name_pos == -1:
            return None

        context_start = max(0, name_pos - 80)
        context_end = min(len(text), name_pos + len(candidate_name) + 80)
        context = text[context_start:context_end]

        party_pattern = re.compile(r"\b(Democratic|Republican|Libertarian|Green|Independent)\b", re.IGNORECASE)
        match = party_pattern.search(context)

        return match.group(1).title() if match else None

    def _check_incumbent_status(self, text: str, candidate_name: str) -> bool:
        """Check if candidate is mentioned as incumbent with enhanced context matching."""
        # Look for incumbent keywords near the candidate name with broader context
        name_pos = text.lower().find(candidate_name.lower())
        if name_pos == -1:
            return False

        # Expand context window for better detection
        context_start = max(0, name_pos - 120)
        context_end = min(len(text), name_pos + len(candidate_name) + 120)
        context = text[context_start:context_end]

        # Enhanced incumbent patterns
        incumbent_patterns = [
            r"\bincumbent\b",
            r"\bcurrent\s+(?:senator|representative|governor)\b",
            r"\bserving\s+(?:senator|representative|governor)\b",
            r"\breelection\b",
            r"\bdefending\s+(?:seat|office)\b"
        ]
        
        for pattern in incumbent_patterns:
            if re.search(pattern, context, re.IGNORECASE):
                return True
                
        return False

    def _merge_and_deduplicate_structured_candidates(self, candidates: List[DiscoveredCandidate]) -> List[DiscoveredCandidate]:
        """Merge and deduplicate structured candidates by name with normalized source URLs."""
        merged = {}

        for candidate in candidates:
            # Normalize name for deduplication
            name_key = re.sub(r"\s+", " ", candidate.name.strip().lower())

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

                # Merge source lists with efficient deduplication
                if not hasattr(existing, "_src_set"):
                    existing._src_set = {self._normalize_source_url(s) for s in existing.sources}
                
                for source in candidate.sources:
                    norm = self._normalize_source_url(source)
                    if norm not in existing._src_set:
                        existing.sources.append(source)
                        existing._src_set.add(norm)
            else:
                merged[name_key] = candidate

        return list(merged.values())[:8]  # Limit to reasonable number

    def _has_more_trusted_sources(self, candidate1: DiscoveredCandidate, candidate2: DiscoveredCandidate) -> bool:
        """Check if candidate1 has more trusted sources than candidate2."""
        trusted1 = sum(1 for url in candidate1.sources if self._is_trusted_source(str(url)))
        trusted2 = sum(1 for url in candidate2.sources if self._is_trusted_source(str(url)))
        return trusted1 > trusted2

    async def _validate_structured_candidates_with_ai(
        self,
        candidates: List[DiscoveredCandidate],
        race_id: str,
        state: str,
        office_type: str,
        year: int,
        district: Optional[str] = None,
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
                if any(
                    name.lower() in candidate.name.lower() or candidate.name.lower() in name.lower()
                    for name in validated_names
                ):
                    validated_candidates.append(candidate)

            logger.info(f"AI validated {len(validated_candidates)} of {len(candidates)} candidates for {race_id}")
            return validated_candidates[:8]

        except Exception as e:
            logger.warning(f"Error during AI validation for {race_id}: {e}")
            return candidates[:3]  # Fallback
