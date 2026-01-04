"""
Validation and transformation utilities for SmarterVote race publishing.

This module contains utilities for validating, transforming, and enriching
race data before publication.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..schema import RaceJSON

logger = logging.getLogger(__name__)


# Comprehensive office type to display name mapping
OFFICE_DISPLAY_NAMES = {
    # Federal offices
    "senate": "U.S. Senate",
    "house": "U.S. House of Representatives",
    # State executive offices
    "governor": "Governor",
    "lieutenant-governor": "Lieutenant Governor",
    "lieutenant_governor": "Lieutenant Governor",
    "attorney-general": "Attorney General",
    "attorney_general": "Attorney General",
    "secretary-of-state": "Secretary of State",
    "secretary_of_state": "Secretary of State",
    "treasurer": "State Treasurer",
    "state-treasurer": "State Treasurer",
    "comptroller": "Comptroller",
    "auditor": "State Auditor",
    "state-auditor": "State Auditor",
    # State legislative offices
    "state-senate": "State Senate",
    "state_senate": "State Senate",
    "state-house": "State House of Representatives",
    "state_house": "State House of Representatives",
    "state-assembly": "State Assembly",
    "state_assembly": "State Assembly",
    "state-representative": "State Representative",
    # Other statewide offices
    "railroad-commissioner": "Railroad Commissioner",
    "agriculture-commissioner": "Agriculture Commissioner",
    "insurance-commissioner": "Insurance Commissioner",
    "superintendent": "Superintendent of Public Instruction",
    "public-instruction": "Superintendent of Public Instruction",
    # Local offices
    "mayor": "Mayor",
    "city-council": "City Council",
    "city_council": "City Council",
    "county-executive": "County Executive",
    "county_executive": "County Executive",
    "county-commissioner": "County Commissioner",
    "county_commissioner": "County Commissioner",
    "school-board": "School Board",
    "school_board": "School Board",
    "sheriff": "Sheriff",
    "district-attorney": "District Attorney",
    "district_attorney": "District Attorney",
    "judge": "Judge",
    "justice": "Justice",
}


def _infer_office_name(race_id: str) -> Optional[str]:
    """
    Infer the office display name from a race ID.

    Args:
        race_id: Race identifier (e.g., 'mo-senate-2024', 'tx-governor-2024')

    Returns:
        The full office name or None if not found
    """
    race_lower = race_id.lower()

    # Check direct mappings first
    for office_key, display_name in OFFICE_DISPLAY_NAMES.items():
        if office_key in race_lower:
            return display_name

    # Handle state-specific patterns for state legislature
    if "state-sen" in race_lower or "statesenate" in race_lower:
        return "State Senate"
    if "state-rep" in race_lower or "staterep" in race_lower:
        return "State House of Representatives"

    return None


class ValidationUtils:
    """Utilities for validating race data."""

    @staticmethod
    async def validate_arbitrated_data(arbitrated_data: Dict[str, Any]) -> None:
        """
        Validate arbitrated consensus data before transformation.

        TODO: Implement comprehensive validation:
        - Schema validation against expected consensus structure
        - Data completeness checks for required fields
        - Value range validation for numerical data
        - Cross-field consistency validation
        - Confidence score validation and thresholds
        - Source attribution validation
        """
        logger.debug("Validating arbitrated consensus data")

        if not arbitrated_data:
            raise ValueError("Arbitrated data cannot be empty")

        # Basic structure validation
        required_keys = ["race_info", "candidates"]
        for key in required_keys:
            if key not in arbitrated_data:
                logger.warning(f"Missing required key in arbitrated data: {key}")

        logger.debug("Arbitrated data validation completed")

    @staticmethod
    async def validate_race_json(race: RaceJSON) -> None:
        """
        Validate final RaceJSON structure before publishing.

        TODO: Implement comprehensive RaceJSON validation:
        - Pydantic model validation with detailed error reporting
        - Business rule validation (election dates, candidate counts)
        - Cross-candidate consistency checks
        - Issue stance completeness validation
        - Source URL accessibility validation
        - Data freshness and timestamp validation
        """
        logger.debug(f"Validating RaceJSON for race {race.id}")

        try:
            # Pydantic model validation
            race.model_validate(race.model_dump())

            # Additional business rule validation
            if not race.id.strip():
                raise ValueError("Race ID cannot be empty")

            if len(race.candidates) == 0:
                raise ValueError("Race must have at least one candidate")

            logger.debug(f"RaceJSON validation passed for race {race.id}")

        except Exception as e:
            logger.error(f"RaceJSON validation failed for race {race.id}: {e}")
            raise ValueError(f"RaceJSON validation failed: {e}")


class TransformationUtils:
    """Utilities for transforming and enriching race data."""

    @staticmethod
    async def extract_race_metadata(race_id: str, arbitrated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and enrich race metadata from arbitrated consensus data.

        TODO: Implement comprehensive metadata extraction:
        - Intelligent data parsing from multiple sources
        - Geographic data enrichment (coordinates, demographics)
        - Historical context integration (previous election results)
        - Candidate background information integration
        - Media coverage and public sentiment analysis
        - Election law and procedure information
        """
        logger.debug(f"Extracting race metadata for {race_id}")

        metadata = {
            "race_id": race_id,
            "office": "Unknown Office",
            "jurisdiction": "Unknown Jurisdiction",
            "election_date": None,
            "candidates_count": 0,
            "last_updated": datetime.utcnow(),
        }

        try:
            # Extract from consensus data if available
            consensus_data = arbitrated_data.get("race_info", {})
            # Fallback to consensus_data for backwards compatibility
            if not consensus_data:
                consensus_data = arbitrated_data.get("consensus_data", {})

            # Office information
            if "office" in consensus_data:
                metadata["office"] = consensus_data["office"]
            elif "position" in consensus_data:
                metadata["office"] = consensus_data["position"]

            # Jurisdiction information
            if "jurisdiction" in consensus_data:
                metadata["jurisdiction"] = consensus_data["jurisdiction"]
            elif "district" in consensus_data:
                metadata["jurisdiction"] = consensus_data["district"]
            elif "state" in consensus_data:
                metadata["jurisdiction"] = consensus_data["state"]

            # Title information
            if "race_title" in consensus_data:
                metadata["title"] = consensus_data["race_title"]
            elif "title" in consensus_data:
                metadata["title"] = consensus_data["title"]

            # Parse election date
            if "election_date" in consensus_data:
                date_str = consensus_data["election_date"]
                if isinstance(date_str, str):
                    # Try to parse various date formats
                    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"]:
                        try:
                            metadata["election_date"] = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
                elif isinstance(date_str, datetime):
                    metadata["election_date"] = date_str

            # Count candidates
            if "candidates" in arbitrated_data:
                metadata["candidates_count"] = len(arbitrated_data["candidates"])

            # Infer from race_id if possible
            race_parts = race_id.split("-")
            if len(race_parts) >= 2:
                # Extract state/jurisdiction from race ID
                potential_state = race_parts[0].upper()
                if len(potential_state) == 2:  # State abbreviation
                    if metadata["jurisdiction"] == "Unknown Jurisdiction":
                        metadata["jurisdiction"] = potential_state

                # Extract office type from race ID using comprehensive mapping
                office_name = _infer_office_name(race_id)
                if office_name and metadata["office"] == "Unknown Office":
                    metadata["office"] = office_name

                # Extract year from race ID
                if race_parts[-1].isdigit() and len(race_parts[-1]) == 4:
                    year = int(race_parts[-1])
                    if 2020 <= year <= 2030:  # Reasonable range
                        # Assume November election
                        metadata["election_date"] = datetime(year, 11, 5)

        except Exception as e:
            logger.warning(f"Error extracting race metadata for {race_id}: {e}")

        logger.debug(f"Extracted metadata for {race_id}: {metadata}")
        return metadata


def initialize_transformation_pipeline() -> List[str]:
    """
    Initialize the data transformation pipeline steps.

    TODO: Implement comprehensive transformation pipeline:
    - Data normalization and standardization
    - Source attribution and lineage tracking
    - Confidence score calculation and aggregation
    - Issue categorization and tagging
    - Temporal analysis and trend detection
    - Cross-reference validation with external sources
    """
    return [
        "data_normalization",
        "source_attribution",
        "confidence_calculation",
        "issue_categorization",
        "temporal_analysis",
        "cross_reference_validation",
        "metadata_enrichment",
        "final_validation",
    ]


def initialize_validation_rules() -> Dict[str, Any]:
    """
    Initialize validation rules for race data.

    TODO: Implement comprehensive validation rules:
    - Required field definitions with data types
    - Value range constraints for numerical fields
    - Format validation for dates, URLs, and identifiers
    - Business logic rules for election data
    - Cross-field dependency validation
    - Regional and jurisdictional rule variations
    """
    return {
        "required_fields": [
            "id",
            "office",
            "jurisdiction",
            "candidates",
            "last_updated",
        ],
        "field_types": {
            "id": str,
            "office": str,
            "jurisdiction": str,
            "candidates": list,
            "election_date": datetime,
        },
        "constraints": {
            "candidates_min_count": 1,
            "candidates_max_count": 20,
            "confidence_min": 0.0,
            "confidence_max": 1.0,
        },
        "formats": {
            "race_id_pattern": r"^[a-z]{2}-[a-z]+-\d{4}$",
            "url_schemes": ["http", "https"],
        },
    }
