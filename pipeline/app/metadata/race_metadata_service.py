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

from ..schema import CanonicalIssue, ConfidenceLevel, RaceMetadata

logger = logging.getLogger(__name__)


class RaceMetadataService:
    """Service for extracting structured race metadata early in pipeline."""

    def __init__(self):
        """Initialize the race metadata service."""
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

        # State-specific issue priorities
        self.state_issue_priorities = {
            "CA": ["Climate/Energy", "Tech & AI", "Healthcare", "Immigration"],
            "TX": ["Immigration", "Economy", "Climate/Energy", "Education"],
            "FL": ["Climate/Energy", "Immigration", "Healthcare", "Economy"],
            "NY": ["Healthcare", "Economy", "Climate/Energy", "Social Justice"],
            "MO": ["Economy", "Healthcare", "Agriculture", "Education"],
            "OH": ["Economy", "Healthcare", "Education", "Immigration"],
            # Add more states as needed
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
            # Parse race_id components
            state, office_type, year, district = self._parse_race_id(race_id)

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
                major_issues=major_issues,
                geographic_keywords=geographic_keywords,
                confidence=ConfidenceLevel.HIGH,
            )

            logger.info(f"✅ Extracted metadata for {race_id}: {office_info['full_name']} in {jurisdiction}")
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
        """Get major issues for this race type and state."""
        # Start with office-based issues
        office_info = self._get_office_info(office_type)
        major_issues = office_info.get("major_issues", [])

        # Add state-specific priorities
        state_issues = self.state_issue_priorities.get(state, [])

        # Combine and deduplicate while preserving order
        combined_issues = []
        for issue in major_issues + state_issues:
            if issue not in combined_issues:
                combined_issues.append(issue)

        # Limit to top 6 issues
        return combined_issues[:6]

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
            major_issues=["Economy", "Healthcare"],
            geographic_keywords=[],
            confidence=ConfidenceLevel.LOW,
        )
