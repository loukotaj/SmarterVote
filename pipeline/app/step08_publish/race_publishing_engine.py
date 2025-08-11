"""
Race Publishing Engine for SmarterVote Pipeline

This module handles the final publication of race analysis data to multiple storage systems.
It transforms arbitrated consensus data into standardized RaceJSON format and publishes
to local storage, cloud storage, databases, and notification systems.

Key responsibilities:
- Transform arbitrated data into structured RaceJSON format
- Validate and enrich race data with metadata
- Publish to multiple storage backends (local, cloud, database)
- Send completion notifications and webhook callbacks
- Maintain publication audit trails and versioning
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..schema import CanonicalIssue, ConfidenceLevel, IssueStance, RaceJSON
from ..utils.validation_utils import (
    TransformationUtils,
    ValidationUtils,
    initialize_transformation_pipeline,
    initialize_validation_rules,
)
from .publication_types import PublicationConfig, PublicationResult, PublicationTarget
from .publishers import Publishers

logger = logging.getLogger(__name__)


class RacePublishingEngine:
    """
    Advanced publishing engine for SmarterVote race analysis data.

    This engine handles the transformation of arbitrated consensus data into
    standardized RaceJSON format and publishes it across multiple systems.
    """

    def __init__(self, config: Optional[PublicationConfig] = None):
        """
        Initialize the publishing engine.

        Args:
            config: Publication configuration settings
        """
        self.config = config or PublicationConfig(
            default_targets=[PublicationTarget.LOCAL_FILE], local_output_dir="data/published"
        )

        # Initialize publishers and utilities
        self.publishers = Publishers(self.config)
        self.validation_utils = ValidationUtils()
        self.transformation_utils = TransformationUtils()
        self.transformation_pipeline = initialize_transformation_pipeline()
        self.validation_rules = initialize_validation_rules()

        # Publication tracking
        self.publication_history: List[PublicationResult] = []
        self.active_publications: Dict[str, asyncio.Task] = {}

        logger.info(f"Publishing engine initialized with output directory: {self.config.local_output_dir}")

    async def create_race_json(
        self,
        race_id: str,
        arbitrated_data: Dict[str, Any],
        race_metadata: Optional[Any] = None,
    ) -> RaceJSON:
        """
        Transform arbitrated consensus data into standardized RaceJSON format.

        Args:
            race_id: Unique identifier for the race
            arbitrated_data: Consensus data from arbitration engine
            race_metadata: Metadata from discovery phase

        Returns:
            Validated RaceJSON object ready for publication

        TODO: Implement advanced transformation features:
        - Multi-source data fusion and conflict resolution
        - Temporal analysis and trend detection
        - Cross-reference validation with external sources
        - Intelligent metadata enrichment
        - Source attribution and lineage tracking
        - Generate publication metadata and versioning
        """
        logger.info(f"Creating RaceJSON for race {race_id}")

        try:
            # Validate input data
            await self.validation_utils.validate_arbitrated_data(arbitrated_data)

            # Extract base race information - prioritize race_metadata if available
            if race_metadata:
                race_info = {
                    "title": f"{race_metadata.full_office_name} - {race_metadata.jurisdiction} {race_metadata.year}",
                    "office": race_metadata.full_office_name,
                    "jurisdiction": race_metadata.jurisdiction,
                    "election_date": race_metadata.election_date,
                }
                logger.info(f"Using provided race metadata for {race_id}")
            else:
                race_info = await self.transformation_utils.extract_race_metadata(race_id, arbitrated_data)

                logger.info(f"Extracted race metadata from arbitrated data for {race_id}")

            # Process candidate data
            candidates = await self._extract_candidates(arbitrated_data)

            # Generate publication metadata
            metadata = await self._generate_publication_metadata(race_id, arbitrated_data)

            # Create RaceJSON object
            race = RaceJSON(
                id=race_id,
                election_date=race_info.get("election_date", datetime.utcnow()),
                candidates=candidates,
                updated_utc=datetime.utcnow(),
                title=race_info.get("title", f"Electoral Race {race_id}"),
                office=race_info.get("office", "Unknown Office"),
                jurisdiction=race_info.get("jurisdiction", "Unknown Jurisdiction"),
                race_metadata=race_metadata,  # Include the full metadata
            )

            # Apply validation rules
            await self.validation_utils.validate_race_json(race)

            logger.info(f"Successfully created RaceJSON for race {race_id}")
            return race

        except Exception as e:
            logger.error(f"Failed to create RaceJSON for race {race_id}: {e}")
            raise

    async def publish_race(self, race: RaceJSON, targets: Optional[List[PublicationTarget]] = None) -> List[PublicationResult]:
        """
        Publish race data to configured targets.

        Args:
            race: Race data to publish
            targets: Optional list of publication targets (uses default if None)

        Returns:
            List of publication results for each target

        TODO: Implement advanced publishing features:
        - Intelligent target selection based on data characteristics
        - Parallel publishing with dependency management
        - Retry logic with exponential backoff
        - Publication rollback on critical failures
        - Real-time monitoring and alerting
        - Performance optimization and caching
        """
        logger.info(f"Publishing race {race.id} to targets")

        # Use default targets if none specified
        if targets is None:
            targets = self.config.default_targets

        results = []

        try:
            # Create publication tasks for all targets
            tasks = []
            for target in targets:
                task = asyncio.create_task(self._publish_to_target(race, target))
                task_key = f"{race.id}_{target.value}"
                self.active_publications[task_key] = task
                tasks.append(task)

            # Execute all publications concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results and handle exceptions
            final_results = []
            for i, result in enumerate(results):
                target = targets[i]
                if isinstance(result, Exception):
                    logger.error(f"Publication to {target.value} failed with exception: {result}")
                    final_results.append(
                        PublicationResult(
                            target=target,
                            success=False,
                            timestamp=datetime.now(timezone.utc),
                            message=f"Publication failed: {str(result)}",
                            metadata={"error_type": type(result).__name__},
                        )
                    )
                else:
                    final_results.append(result)

                # Clean up task tracking
                task_key = f"{race.id}_{target.value}"
                if task_key in self.active_publications:
                    del self.active_publications[task_key]

        except Exception as e:
            logger.error(f"Critical error during race publication: {e}")
            raise

        # Log publication summary
        successful = [r for r in final_results if r.success]
        failed = [r for r in final_results if not r.success]

        logger.info(f"Race {race.id} publication complete: {len(successful)} successful, {len(failed)} failed")

        if failed:
            logger.warning(f"Failed publications for race {race.id}: {[f.target.value for f in failed]}")

        # Store in publication history
        self.publication_history.extend(final_results)

        return final_results

    async def _publish_to_target(self, race: RaceJSON, target: PublicationTarget) -> PublicationResult:
        """
        Publish race data to a specific target.

        Args:
            race: Race data to publish
            target: Publication target

        Returns:
            Publication result with success status and metadata
        """
        start_time = datetime.now(timezone.utc)

        try:
            if target == PublicationTarget.LOCAL_FILE:
                await self.publishers.publish_to_local_file(race)
            elif target == PublicationTarget.CLOUD_STORAGE:
                await self.publishers.publish_to_cloud_storage(race)
            elif target == PublicationTarget.DATABASE:
                await self.publishers.publish_to_database(race)
            elif target == PublicationTarget.WEBHOOK:
                await self.publishers.publish_to_webhooks(race)
            elif target == PublicationTarget.PUBSUB:
                await self.publishers.publish_to_pubsub(race)
            elif target == PublicationTarget.API_ENDPOINT:
                await self.publishers.publish_to_api_endpoint(race)
            else:
                raise ValueError(f"Unknown publication target: {target}")

            return PublicationResult(
                target=target,
                success=True,
                timestamp=start_time,
                message=f"Successfully published to {target.value}",
                metadata={"duration_ms": (datetime.now(timezone.utc) - start_time).total_seconds() * 1000},
            )

        except Exception as e:
            logger.error(f"Failed to publish race {race.id} to {target.value}: {e}")
            return PublicationResult(
                target=target,
                success=False,
                timestamp=start_time,
                message=f"Publication failed: {str(e)}",
                metadata={"error_type": type(e).__name__},
            )

    async def _validate_arbitrated_data(self, arbitrated_data: Dict[str, Any]) -> None:
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

    async def _validate_race_json(self, race: RaceJSON) -> None:
        """
        Validate a RaceJSON object.

        Args:
            race: RaceJSON object to validate

        Raises:
            ValidationError: If race data is invalid
        """
        await self.validation_utils.validate_race_json(race)

    async def _extract_race_metadata(self, race_id: str, arbitrated_data: Dict[str, Any]) -> Dict[str, Any]:
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
            elif "district" in consensus_data:
                metadata["jurisdiction"] = consensus_data["district"]
            elif "state" in consensus_data:
                metadata["jurisdiction"] = consensus_data["state"]

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

            # Infer from race_id if possible
            race_parts = race_id.split("-")
            if len(race_parts) >= 2:
                # Extract state/jurisdiction from race ID
                potential_state = race_parts[0].upper()
                if len(potential_state) == 2:  # State abbreviation
                    if metadata["jurisdiction"] == "Unknown Jurisdiction":
                        metadata["jurisdiction"] = potential_state

                # Extract office type from race ID
                if "senate" in race_id.lower():
                    if metadata["office"] == "Unknown Office":
                        metadata["office"] = "U.S. Senate"
                elif "house" in race_id.lower():
                    if metadata["office"] == "Unknown Office":
                        metadata["office"] = "U.S. House of Representatives"
                elif "governor" in race_id.lower():
                    if metadata["office"] == "Unknown Office":
                        metadata["office"] = "Governor"

                # Extract year from race ID
                if race_parts[-1].isdigit() and len(race_parts[-1]) == 4:
                    year = int(race_parts[-1])
                    if 2020 <= year <= 2030:  # Reasonable range
                        # Assume November election
                        metadata["election_date"] = datetime(year, 11, 5)

        except Exception as e:
            logger.warning(f"Error extracting race metadata for {race_id}: {e}")

        logger.debug(f"Extracted metadata for race {race_id}: {metadata}")
        return metadata

    async def _extract_candidates(self, arbitrated_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract candidate information from arbitrated data.

        Implements comprehensive candidate extraction from consensus summaries
        including policy positions, biographical data, and issue stances.
        """
        candidates = []

        try:
            consensus_data = arbitrated_data.get("consensus_data", {})
            candidates_data = consensus_data.get("candidates", [])

            # If candidates are directly provided, use them
            for candidate_info in candidates_data:
                candidate = {
                    "name": candidate_info.get("name", "Unknown Candidate"),
                    "party": candidate_info.get("party", "Unknown Party"),
                    "issue_stances": candidate_info.get("issue_stances", {}),
                    "biographical_info": candidate_info.get("biographical_info", {}),
                    "confidence_scores": candidate_info.get("confidence_scores", {}),
                    "sources": candidate_info.get("sources", []),
                }
                candidates.append(candidate)

            # If no direct candidates, extract from arbitrated summaries
            if not candidates:
                arbitrated_summaries = arbitrated_data.get("arbitrated_summaries", [])
                candidate_map = {}

                for summary in arbitrated_summaries:
                    candidate_name = summary.get("candidate_name")
                    if candidate_name:
                        if candidate_name not in candidate_map:
                            candidate_map[candidate_name] = {
                                "name": candidate_name,
                                "party": summary.get("party", "Unknown Party"),
                                "summary": "",
                                "issues": {},
                                "top_donors": [],
                                "website": None,
                                "social_media": {},
                                "incumbent": False,
                            }

                        # Add candidate information based on query type
                        if summary.get("query_type") == "candidate_summary":
                            candidate_map[candidate_name]["summary"] = summary.get("content", "")
                        elif summary.get("query_type") == "issue_stance":
                            issue_name = summary.get("issue", "Unknown Issue")
                            # Try to map to canonical issue
                            canonical_issue = None
                            for ci in CanonicalIssue:
                                if ci.value.lower() == issue_name.lower():
                                    canonical_issue = ci
                                    break

                            if canonical_issue:
                                # Create IssueStance object
                                confidence_str = summary.get("confidence", "unknown")
                                confidence_level = ConfidenceLevel.UNKNOWN
                                for cl in ConfidenceLevel:
                                    if cl.value.lower() == confidence_str.lower():
                                        confidence_level = cl
                                        break

                                issue_stance = IssueStance(
                                    issue=canonical_issue,
                                    stance=summary.get("content", ""),
                                    confidence=confidence_level,
                                    sources=[],
                                )
                                candidate_map[candidate_name]["issues"][canonical_issue] = issue_stance

                candidates = list(candidate_map.values())

            # If still no candidates, create a placeholder for minimal data scenarios
            if not candidates:
                candidates = [
                    {
                        "name": "Candidate Information Pending",
                        "party": "Unknown Party",
                        "summary": "Candidate information not yet available",
                        "issues": {},
                        "top_donors": [],
                        "website": None,
                        "social_media": {},
                        "incumbent": False,
                    }
                ]

            logger.debug(f"Extracted {len(candidates)} candidates from arbitrated data")

        except Exception as e:
            logger.warning(f"Error extracting candidates: {e}")

        return candidates

    async def _generate_publication_metadata(self, race_id: str, arbitrated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate publication metadata for the race.

        Includes information about data sources, processing timestamps,
        confidence metrics, and publication audit trail.
        """
        metadata = {
            "race_id": race_id,
            "processing_timestamp": datetime.utcnow(),
            "data_sources": arbitrated_data.get("sources", []),
            "confidence_metrics": arbitrated_data.get("confidence_metrics", {}),
            "processing_pipeline": self.transformation_pipeline,
            "validation_rules": list(self.validation_rules.keys()),
        }

        return metadata

    def get_publication_history(self, race_id: Optional[str] = None) -> List[PublicationResult]:
        """
        Get publication history, optionally filtered by race ID.

        Args:
            race_id: Optional race ID to filter results

        Returns:
            List of publication results
        """
        if race_id:
            return [r for r in self.publication_history if race_id in str(r.metadata)]
        return self.publication_history.copy()

    def get_active_publications(self) -> Dict[str, asyncio.Task]:
        """
        Get currently active publication tasks.

        Returns:
            Dictionary of active publication tasks by key
        """
        return self.active_publications.copy()

    def get_published_races(self) -> List[str]:
        """
        Get list of published race IDs from local storage.

        Returns:
            List of race IDs that have been published to local files
        """
        try:
            output_dir = Path(self.config.local_output_dir)
            if not output_dir.exists():
                return []

            race_files = output_dir.glob("*.json")
            race_ids = []

            for race_file in race_files:
                # Skip backup files
                if ".backup" in race_file.name:
                    continue

                # Extract race ID from filename (remove .json extension)
                race_id = race_file.stem
                race_ids.append(race_id)

            return sorted(race_ids)

        except Exception as e:
            logger.error(f"Failed to get published races: {e}")
            return []

    def get_race_data(self, race_id: str) -> Optional[Dict[str, Any]]:
        """
        Get race data for a specific race ID from local storage.

        Args:
            race_id: Race ID to retrieve data for

        Returns:
            Race data as dictionary, or None if not found
        """
        try:
            output_file = Path(self.config.local_output_dir) / f"{race_id}.json"

            if not output_file.exists():
                return None

            with open(output_file, "r", encoding="utf-8") as f:
                return json.load(f)

        except Exception as e:
            logger.error(f"Failed to get race data for {race_id}: {e}")
            return None

    async def cleanup_old_publications(self, retention_days: int) -> int:
        """
        Clean up old publication files based on retention policy.

        Args:
            retention_days: Number of days to retain files

        Returns:
            Number of files cleaned up
        """
        try:
            output_dir = Path(self.config.local_output_dir)
            if not output_dir.exists():
                return 0

            cutoff_time = datetime.now().timestamp() - (retention_days * 24 * 3600)
            cleaned_count = 0

            for race_file in output_dir.glob("*.json"):
                # Skip backup files
                if ".backup" in race_file.name:
                    continue

                # Check file modification time
                file_mtime = race_file.stat().st_mtime
                if file_mtime < cutoff_time:
                    logger.info(f"Cleaning up old publication file: {race_file}")
                    race_file.unlink()
                    cleaned_count += 1

            logger.info(f"Cleaned up {cleaned_count} old publication files")
            return cleaned_count

        except Exception as e:
            logger.error(f"Failed to cleanup old publications: {e}")
            return 0
