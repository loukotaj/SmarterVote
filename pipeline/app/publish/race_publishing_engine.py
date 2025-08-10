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
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..schema import RaceJSON
from .publication_types import PublicationConfig, PublicationResult, PublicationTarget
from .publishers import Publishers
from .validation_utils import (
    TransformationUtils,
    ValidationUtils,
    initialize_transformation_pipeline,
    initialize_validation_rules,
)

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
            default_targets=[PublicationTarget.LOCAL_FILE],
            local_output_dir="data/published"
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
            race_metadata: Optional metadata from discovery phase

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
                candidates=candidates,
                metadata=metadata,
                last_updated=datetime.utcnow(),
                title=race_info.get("title", f"Race {race_id}"),
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