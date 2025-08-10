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
        self.config = config or PublicationConfig(output_directory=Path("data/published"))

        # Ensure output directory exists
        self.config.output_directory.mkdir(parents=True, exist_ok=True)

        # Publication tracking
        self.publication_history: List[PublicationResult] = []
        self.active_publications: Dict[str, asyncio.Task] = {}

        # Initialize utilities
        self.validation_rules = initialize_validation_rules()
        self.transformation_pipeline = initialize_transformation_pipeline()
        self.validation_utils = ValidationUtils(self.validation_rules)
        self.transformation_utils = TransformationUtils()
        self.publishers = Publishers(self.config)

        logger.info(f"Publishing engine initialized with output directory: {self.config.output_directory}")

    async def create_race_json(self, race_id: str, arbitrated_data: Dict[str, Any]) -> RaceJSON:
        """
        Transform arbitrated data into standardized RaceJSON format.

        Args:
            race_id: Unique identifier for the race
            arbitrated_data: Consensus data from arbitration engine

        Returns:
            Complete RaceJSON object ready for publication

        TODO: Implement comprehensive data transformation pipeline:
        - Extract candidate information from arbitrated summaries
        - Parse office, jurisdiction, and election metadata
        - Map confidence levels to data quality indicators
        - Generate structured issue positions and policy stances
        - Create citation and source reference mappings
        - Validate data completeness and consistency
        - Apply data enrichment from external sources
        - Generate publication metadata and versioning
        """
        logger.info(f"Creating RaceJSON for race {race_id}")

        try:
            # Validate input data
            await self.validation_utils.validate_arbitrated_data(arbitrated_data)

            # Extract base race information
            race_info = await self.transformation_utils.extract_race_metadata(race_id, arbitrated_data)

            # Process candidate data
            candidates = await self.transformation_utils.extract_candidates(arbitrated_data)

            # Generate publication metadata
            metadata = await self.transformation_utils.generate_publication_metadata(race_id, arbitrated_data)

            # Create RaceJSON object
            race = RaceJSON(
                id=race_id,
                election_date=race_info.get("election_date", datetime(2024, 11, 5)),
                candidates=candidates,
                updated_utc=datetime.now(timezone.utc),
                generator=metadata.get("generators", ["gpt-4o", "claude-3.5", "grok-3"]),
                title=race_info.get("title", f"Electoral Race {race_id}"),
                office=race_info.get("office", "Unknown Office"),
                jurisdiction=race_info.get("jurisdiction", "Unknown Jurisdiction"),
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
        Publish race data to specified targets.

        Args:
            race: Complete race object to publish
            targets: List of publication targets (all if None)

        Returns:
            List of publication results for each target

        TODO: Implement parallel publication to multiple targets:
        - Local file system with versioning and backup
        - Cloud storage (GCS, S3, Azure) with CDN integration
        - Database systems (PostgreSQL, MongoDB, BigQuery)
        - Real-time notification systems (Pub/Sub, WebSockets)
        - Webhook endpoints for external system integration
        - API endpoints for immediate data availability
        - Content delivery networks for public access
        - Search index updates for discovery
        """
        if targets is None:
            # Auto-detect environment and choose appropriate targets
            targets = self._get_environment_specific_targets()

        logger.info(f"Publishing race {race.id} to targets: {[t.value for t in targets]}")

        results = []

        try:
            # Create tasks for parallel publication
            tasks = []
            for target in targets:
                task_key = f"{race.id}_{target.value}"
                task = asyncio.create_task(self._publish_to_target(race, target))
                self.active_publications[task_key] = task
                tasks.append(task)

            # Wait for all publications to complete
            completed_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for i, result in enumerate(completed_results):
                target = targets[i]
                if isinstance(result, Exception):
                    # Handle exception as failed publication
                    error_result = PublicationResult(
                        target=target,
                        success=False,
                        timestamp=datetime.now(timezone.utc),
                        message=f"Publication failed: {str(result)}",
                        metadata={"error_type": type(result).__name__},
                    )
                    results.append(error_result)
                    logger.error(f"Failed to publish race {race.id} to {target.value}: {result}")
                else:
                    results.append(result)

                # Clean up task tracking
                task_key = f"{race.id}_{target.value}"
                if task_key in self.active_publications:
                    del self.active_publications[task_key]

        except Exception as e:
            logger.error(f"Critical error during race publication: {e}")
            raise

        # Log publication summary
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        logger.info(f"Race {race.id} publication complete: {len(successful)} successful, {len(failed)} failed")

        if failed:
            logger.warning(f"Failed publications for race {race.id}: {[f.target.value for f in failed]}")

        return results

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

    def _get_environment_specific_targets(self) -> List[PublicationTarget]:
        """Determine publication targets based on environment."""
        # Default targets for development/testing
        default_targets = [PublicationTarget.LOCAL_FILE]

        # Add cloud targets in production environment
        import os

        if os.getenv("ENVIRONMENT", "development") == "production":
            default_targets.extend([PublicationTarget.CLOUD_STORAGE, PublicationTarget.DATABASE, PublicationTarget.PUBSUB])

        return default_targets

    def get_publication_history(self, race_id: Optional[str] = None) -> List[PublicationResult]:
        """
        Get publication history for all races or a specific race.

        Args:
            race_id: Optional race ID to filter history

        Returns:
            List of publication results
        """
        if race_id:
            return [r for r in self.publication_history if race_id in str(r.metadata)]
        return self.publication_history.copy()

    def get_published_races(self) -> List[str]:
        """
        Get list of successfully published race IDs.

        Returns:
            List of race IDs that have been published

        TODO: Implement comprehensive race listing:
        - Scan multiple storage backends for published races
        - Aggregate publication status across targets
        - Include publication timestamps and versions
        - Filter by publication status and targets
        - Support pagination for large race counts
        - Include metadata and quality scores
        """
        published_files = list(self.config.output_directory.glob("*.json"))
        return [f.stem for f in published_files]

    def get_race_data(self, race_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve published race data by race ID.

        Args:
            race_id: Race identifier to retrieve

        Returns:
            Race data dictionary if found, None otherwise

        TODO: Implement comprehensive race data retrieval:
        - Search across multiple storage backends
        - Handle different data formats and versions
        - Include caching for frequently accessed races
        - Support partial data retrieval and field selection
        - Implement access control and authorization
        - Add data freshness indicators and timestamps
        """
        race_file = self.config.output_directory / f"{race_id}.json"

        if race_file.exists():
            try:
                with open(race_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load race data for {race_id}: {e}")
                return None

        return None
