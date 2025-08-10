"""
Publish Service for SmarterVote Pipeline

This service orchestrates the publication of race analysis data to multiple targets
including local storage, cloud storage, databases, and notification systems.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..schema import ProcessingJob, ProcessingStatus, RaceJSON
from .race_publishing_engine import PublicationConfig, PublicationTarget, RacePublishingEngine

logger = logging.getLogger(__name__)


class PublishService:
    """
    Service for publishing processed race data to multiple targets.

    This service handles the final step of the pipeline by taking arbitrated
    race data and publishing it to configured storage and notification systems.
    """

    def __init__(self):
        """Initialize the publish service with configuration."""
        self.config = PublicationConfig(
            output_directory=os.getenv("DATA_PUBLISH_DIR", "data/published"),
            enable_cloud_storage=os.getenv("ENABLE_CLOUD_STORAGE", "true").lower() == "true",
            enable_database=os.getenv("ENABLE_DATABASE", "true").lower() == "true",
            enable_webhooks=os.getenv("ENABLE_WEBHOOKS", "true").lower() == "true",
            enable_notifications=os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true",
        )

        self.engine = RacePublishingEngine(self.config)
        logger.info("Publish service initialized")

    async def process_job(self, job: ProcessingJob, arbitrated_data: Dict[str, Any]) -> ProcessingJob:
        """
        Process a publish job by creating and publishing RaceJSON data.

        Args:
            job: The processing job to update
            arbitrated_data: Arbitrated consensus data from previous pipeline step

        Returns:
            Updated job with publish step completed
        """
        logger.info(f"Starting publish step for job {job.job_id}, race {job.race_id}")

        try:
            # Create RaceJSON from arbitrated data
            race = await self.engine.create_race_json(job.race_id, arbitrated_data)

            # Determine publication targets based on configuration
            targets = self._get_enabled_targets()

            # Publish to all enabled targets
            results = await self.engine.publish_race(race, targets)

            # Check if all critical targets succeeded
            critical_targets = [PublicationTarget.LOCAL_FILE]
            critical_success = all(r.success for r in results if r.target in critical_targets)

            if critical_success:
                job.step_publish = True
                job.status = ProcessingStatus.COMPLETED
                job.completed_at = datetime.now(timezone.utc)
                logger.info(f"Successfully completed publish step for job {job.job_id}")
            else:
                failed_targets = [r.target.value for r in results if not r.success]
                error_msg = f"Critical publication targets failed: {failed_targets}"
                job.error_message = error_msg
                job.status = ProcessingStatus.FAILED
                logger.error(f"Publish step failed for job {job.job_id}: {error_msg}")

        except Exception as e:
            job.error_message = f"Publish step failed: {str(e)}"
            job.status = ProcessingStatus.FAILED
            logger.error(f"Publish step failed for job {job.job_id}: {e}", exc_info=True)

        return job

    def _get_enabled_targets(self) -> List[PublicationTarget]:
        """Get list of enabled publication targets based on configuration."""
        targets = [PublicationTarget.LOCAL_FILE]  # Always enabled

        if self.config.enable_cloud_storage:
            targets.append(PublicationTarget.CLOUD_STORAGE)

        if self.config.enable_database:
            targets.append(PublicationTarget.DATABASE)

        if self.config.enable_webhooks:
            targets.append(PublicationTarget.WEBHOOK)

        if self.config.enable_notifications:
            targets.append(PublicationTarget.PUBSUB)

        return targets

    async def get_published_races(self) -> List[str]:
        """Get list of published race IDs."""
        return self.engine.get_published_races()

    async def get_race_data(self, race_id: str) -> Optional[Dict[str, Any]]:
        """Get published race data by ID."""
        return self.engine.get_race_data(race_id)

    async def cleanup_old_publications(self, retention_days: Optional[int] = None) -> int:
        """Clean up old publication files."""
        return await self.engine.cleanup_old_publications(retention_days)
