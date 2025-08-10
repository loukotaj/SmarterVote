"""
Validation and transformation utilities for SmarterVote Pipeline.

This module contains validation logic and data transformation utilities
for race publishing operations.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..schema import CanonicalIssue, ConfidenceLevel, RaceJSON

logger = logging.getLogger(__name__)


class ValidationUtils:
    """Utilities for validating race data before publication."""

    def __init__(self, validation_rules: Dict[str, Any]):
        """Initialize with validation rules."""
        self.validation_rules = validation_rules

    async def validate_arbitrated_data(self, arbitrated_data: Dict[str, Any]) -> None:
        """
        Validate arbitrated data before transformation.

        TODO: Implement comprehensive data validation:
        - Schema validation against expected data structure
        - Consensus quality threshold checks
        - Required field presence validation
        - Data type and format validation
        - Confidence level validation
        - Source reference validation
        - Content length and quality checks
        - Cross-reference consistency validation
        """
        if not arbitrated_data:
            raise ValueError("Arbitrated data cannot be empty")

        # Basic validation placeholder
        required_fields = ["consensus_data", "overall_confidence"]
        for field in required_fields:
            if field not in arbitrated_data:
                logger.warning(f"Missing expected field in arbitrated data: {field}")

    async def validate_race_json(self, race: RaceJSON) -> None:
        """
        Validate RaceJSON object before publication.

        Implements comprehensive validation including business rules,
        data completeness, and publication readiness checks.
        """
        validation_errors = []

        try:
            # Basic Pydantic model validation
            race.model_validate(race.model_dump())
        except Exception as e:
            validation_errors.append(f"Pydantic validation failed: {e}")

        # Business rule validations
        if not race.id or not race.id.strip():
            validation_errors.append("Race ID is required and cannot be empty")

        if not race.title or not race.title.strip():
            validation_errors.append("Race title is required and cannot be empty")

        if not race.candidates:
            validation_errors.append("Race must have at least one candidate")

        # Validate candidates
        candidate_names = set()
        for i, candidate in enumerate(race.candidates):
            if not candidate.name or not candidate.name.strip():
                validation_errors.append(f"Candidate {i} name is required")

            if candidate.name in candidate_names:
                validation_errors.append(f"Duplicate candidate name: {candidate.name}")
            candidate_names.add(candidate.name)

            if not candidate.summary or len(candidate.summary.strip()) < 10:
                validation_errors.append(f"Candidate {candidate.name} summary is too short (minimum 10 characters)")

        # Date validations
        if race.election_date and race.election_date < datetime(1900, 1, 1):
            validation_errors.append("Election date cannot be before 1900")

        if race.updated_utc and race.updated_utc > datetime.now(timezone.utc):
            validation_errors.append("Updated timestamp cannot be in the future")

        # Check if we have enough high-quality content
        total_content_length = sum(len(candidate.summary) for candidate in race.candidates)
        min_content_length = self.validation_rules.get("min_content_length", 100)

        if total_content_length < min_content_length:
            validation_errors.append(f"Total content length ({total_content_length}) below minimum ({min_content_length})")

        # Validate required fields are present
        required_fields = self.validation_rules.get("required_fields", [])
        race_dict = race.model_dump()

        for field in required_fields:
            if field not in race_dict or not race_dict[field]:
                validation_errors.append(f"Required field missing or empty: {field}")

        # Check for suspicious or invalid data
        if race.office and len(race.office) > 200:
            validation_errors.append("Office name is suspiciously long (>200 characters)")

        if race.jurisdiction and len(race.jurisdiction) > 200:
            validation_errors.append("Jurisdiction name is suspiciously long (>200 characters)")

        # If there are validation errors, raise exception
        if validation_errors:
            error_message = f"RaceJSON validation failed for {race.id}: " + "; ".join(validation_errors)
            logger.error(error_message)
            raise ValueError(error_message)


class TransformationUtils:
    """Utilities for transforming arbitrated data into RaceJSON format."""

    async def extract_race_metadata(self, race_id: str, arbitrated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract race metadata from arbitrated data.

        Implements sophisticated metadata extraction from consensus data
        including parsing dates, offices, and jurisdictions.
        """
        metadata = {
            "title": f"Electoral Race {race_id}",
            "office": "Unknown Office",
            "jurisdiction": "Unknown Jurisdiction",
            "election_date": datetime(2024, 11, 5),
        }

        try:
            # Extract from arbitrated data structure
            consensus_data = arbitrated_data.get("consensus_data", {})

            # Try to extract race title
            if "race_title" in consensus_data:
                metadata["title"] = consensus_data["race_title"]
            elif "title" in consensus_data:
                metadata["title"] = consensus_data["title"]

            # Extract office information
            if "office" in consensus_data:
                metadata["office"] = consensus_data["office"]
            elif "position" in consensus_data:
                metadata["office"] = consensus_data["position"]

            # Extract jurisdiction
            if "jurisdiction" in consensus_data:
                metadata["jurisdiction"] = consensus_data["jurisdiction"]
            elif "state" in consensus_data:
                metadata["jurisdiction"] = consensus_data["state"]

            # Extract election date
            if "election_date" in consensus_data:
                try:
                    if isinstance(consensus_data["election_date"], str):
                        # Try parsing common date formats
                        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"]:
                            try:
                                metadata["election_date"] = datetime.strptime(consensus_data["election_date"], fmt)
                                break
                            except ValueError:
                                continue
                    elif isinstance(consensus_data["election_date"], datetime):
                        metadata["election_date"] = consensus_data["election_date"]
                except Exception as e:
                    logger.warning(f"Failed to parse election date: {e}")

        except Exception as e:
            logger.warning(f"Error extracting race metadata: {e}")

        return metadata

    async def extract_candidates(self, arbitrated_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract candidate information from arbitrated consensus data.

        Implements sophisticated candidate data extraction including
        issue positions, biographical information, and source attribution.
        """
        candidates = []

        try:
            consensus_data = arbitrated_data.get("consensus_data", {})
            candidate_data = consensus_data.get("candidates", {})

            for candidate_name, candidate_info in candidate_data.items():
                if not isinstance(candidate_info, dict):
                    logger.warning(f"Invalid candidate data for {candidate_name}")
                    continue

                candidate = {
                    "name": candidate_name,
                    "summary": candidate_info.get("summary", "No summary available"),
                    "issue_stances": {},
                    "voting_record": [],
                    "endorsements": [],
                    "donors": [],
                    "sources": candidate_info.get("sources", []),
                }

                # Extract issue positions
                if "issues" in candidate_info:
                    for issue_name, issue_data in candidate_info["issues"].items():
                        if isinstance(issue_data, dict):
                            # Map to canonical issue if possible
                            canonical_issue = self._map_to_canonical_issue(issue_name)
                            if canonical_issue:
                                stance = {
                                    "position": issue_data.get("position", "Unknown"),
                                    "confidence": self._map_confidence_to_enum(issue_data.get("confidence", "unknown")),
                                    "sources": issue_data.get("sources", []),
                                    "last_updated": datetime.now(timezone.utc),
                                }
                                candidate["issue_stances"][canonical_issue.value] = stance

                # Extract voting record if available
                if "voting_record" in candidate_info:
                    candidate["voting_record"] = candidate_info["voting_record"]

                # Extract endorsements
                if "endorsements" in candidate_info:
                    candidate["endorsements"] = candidate_info["endorsements"]

                # Extract donor information
                if "donors" in candidate_info:
                    candidate["donors"] = candidate_info["donors"]

                candidates.append(candidate)

        except Exception as e:
            logger.error(f"Error extracting candidates: {e}")
            # Return at least empty candidate structure
            if not candidates:
                candidates = [
                    {
                        "name": "Unknown Candidate",
                        "summary": "Candidate information unavailable",
                        "issue_stances": {},
                        "voting_record": [],
                        "endorsements": [],
                        "donors": [],
                        "sources": [],
                    }
                ]

        return candidates

    def _map_to_canonical_issue(self, issue_name: str) -> Optional[CanonicalIssue]:
        """
        Map arbitrary issue name to canonical issue enum.

        Uses fuzzy matching and keyword detection to map various
        issue descriptions to standardized canonical issues.
        """
        if not issue_name:
            return None

        issue_lower = issue_name.lower().strip()

        # Define keyword mappings for canonical issues
        issue_mappings = {
            CanonicalIssue.HEALTHCARE: ["health", "medical", "medicare", "medicaid", "hospital", "insurance"],
            CanonicalIssue.ECONOMY: ["economy", "economic", "jobs", "employment", "business", "tax", "fiscal", "budget"],
            CanonicalIssue.CLIMATE_ENERGY: ["climate", "environment", "energy", "renewable", "carbon", "pollution"],
            CanonicalIssue.REPRODUCTIVE_RIGHTS: ["abortion", "reproductive", "birth control", "planned parenthood"],
            CanonicalIssue.IMMIGRATION: ["immigration", "immigrant", "border", "citizenship", "refugee"],
            CanonicalIssue.GUNS_SAFETY: ["gun", "firearms", "second amendment", "shooting", "violence"],
            CanonicalIssue.FOREIGN_POLICY: ["foreign", "international", "war", "military", "defense", "diplomacy"],
            CanonicalIssue.SOCIAL_JUSTICE: ["justice", "equality", "civil rights", "discrimination", "racism"],
            CanonicalIssue.EDUCATION: ["education", "school", "teacher", "student", "university", "college"],
            CanonicalIssue.TECH_AI: ["technology", "artificial intelligence", "ai", "tech", "digital", "internet"],
            CanonicalIssue.ELECTION_REFORM: ["election", "voting", "democracy", "campaign", "electoral"],
        }

        # Find best match
        for canonical_issue, keywords in issue_mappings.items():
            if any(keyword in issue_lower for keyword in keywords):
                return canonical_issue

        return None

    def _map_confidence_to_enum(self, confidence_str: str) -> ConfidenceLevel:
        """Map confidence string to ConfidenceLevel enum."""
        if not confidence_str:
            return ConfidenceLevel.UNKNOWN

        confidence_lower = confidence_str.lower().strip()

        if confidence_lower in ["high", "strong", "confident"]:
            return ConfidenceLevel.HIGH
        elif confidence_lower in ["medium", "moderate", "fair"]:
            return ConfidenceLevel.MEDIUM
        elif confidence_lower in ["low", "weak", "poor"]:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.UNKNOWN

    async def generate_publication_metadata(self, race_id: str, arbitrated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate metadata for the publication process.

        Creates comprehensive metadata including processing timestamps,
        confidence metrics, and data quality indicators.
        """
        metadata = {
            "published_utc": datetime.now(timezone.utc),
            "race_id": race_id,
            "processing_version": "1.0",
            "data_quality_score": 0.0,
            "overall_confidence": ConfidenceLevel.UNKNOWN,
            "sources_processed": 0,
            "candidates_found": 0,
            "issues_analyzed": 0,
        }

        try:
            # Extract quality metrics from arbitrated data
            if "overall_confidence" in arbitrated_data:
                confidence_str = arbitrated_data["overall_confidence"]
                metadata["overall_confidence"] = self._map_confidence_to_enum(confidence_str)

            # Calculate data quality score
            consensus_data = arbitrated_data.get("consensus_data", {})
            if "quality_metrics" in consensus_data:
                metrics = consensus_data["quality_metrics"]
                metadata["data_quality_score"] = metrics.get("overall_score", 0.0)
                metadata["sources_processed"] = metrics.get("sources_count", 0)

            # Count candidates and issues
            candidates = consensus_data.get("candidates", {})
            metadata["candidates_found"] = len(candidates)

            # Count unique issues across all candidates
            all_issues = set()
            for candidate_info in candidates.values():
                if isinstance(candidate_info, dict) and "issues" in candidate_info:
                    all_issues.update(candidate_info["issues"].keys())
            metadata["issues_analyzed"] = len(all_issues)

        except Exception as e:
            logger.warning(f"Error generating publication metadata: {e}")

        return metadata


def initialize_validation_rules() -> Dict[str, Any]:
    """Initialize default validation rules for race publishing."""
    return {
        "min_content_length": 100,
        "required_fields": ["id", "title", "candidates"],
        "max_candidate_count": 20,
        "min_candidate_count": 1,
        "max_title_length": 200,
        "max_office_length": 100,
        "max_jurisdiction_length": 100,
    }


def initialize_transformation_pipeline() -> List[str]:
    """Initialize the data transformation pipeline steps."""
    return [
        "validate_input",
        "extract_metadata",
        "extract_candidates",
        "map_canonical_issues",
        "generate_summaries",
        "validate_output",
        "generate_metadata",
    ]