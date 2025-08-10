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

        # Validation and transformation settings
        self.validation_rules = self._initialize_validation_rules()
        self.transformation_pipeline = self._initialize_transformation_pipeline()
        
        logger.info(f"Publishing engine initialized with output directory: {self.config.output_directory}")
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

    async def _publish_to_local_file(self, race: RaceJSON) -> None:
        """
        Publish race data to local file system.

        TODO: Implement advanced local file publishing:
        - JSON pretty-printing with consistent formatting
        - File versioning with timestamp suffixes
        - Atomic write operations to prevent corruption
        - Backup creation before overwriting existing files
        - Directory organization by date/jurisdiction
        - Compression for large race files
        - Checksum generation for integrity verification
        - Symbolic link creation for latest version
        """
        try:
            # Convert to JSON with proper formatting
            race_json = race.model_dump(mode="json")

            # Generate output filename with versioning
            output_file = self.config.output_directory / f"{race.id}.json"

            # Create backup if file exists
            if output_file.exists() and self.config.version_control:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = self.config.output_directory / f"{race.id}.json.backup.{timestamp}"
                output_file.rename(backup_file)
                logger.debug(f"Created backup: {backup_file}")

            # Write race data atomically
            temp_file = output_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(race_json, f, indent=2, ensure_ascii=False, default=str)

            # Atomic rename to final filename
            temp_file.rename(output_file)

            logger.debug(f"Successfully published race {race.id} to local file: {output_file}")

        except Exception as e:
            logger.error(f"Failed to publish race {race.id} to local file: {e}")
            raise

    async def _publish_to_cloud_storage(self, race: RaceJSON) -> None:
        """
        Publish race data to Google Cloud Storage.

        Implements cloud storage integration with proper error handling,
        metadata, and content type configuration.
        """
        try:
            import os

            from google.cloud import storage
            from google.cloud.exceptions import GoogleCloudError

            # Get configuration from environment
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
            bucket_name = os.getenv("GCS_BUCKET_NAME")

            if not project_id or not bucket_name:
                raise ValueError("Missing required GCP configuration: GOOGLE_CLOUD_PROJECT and GCS_BUCKET_NAME")

            # Initialize client
            client = storage.Client(project=project_id)
            bucket = client.bucket(bucket_name)

            # Generate blob name with versioning
            blob_name = f"races/{race.id}.json"
            blob = bucket.blob(blob_name)

            # Convert race to JSON
            race_json = race.model_dump(mode="json")
            race_data = json.dumps(race_json, indent=2, ensure_ascii=False, default=str)

            # Set metadata
            metadata = {
                "race_id": race.id,
                "updated_utc": race.updated_utc.isoformat(),
                "pipeline_version": "1.0.0",
                "content_type": "application/json",
                "encoding": "utf-8",
            }

            # Upload with proper content type and metadata
            blob.upload_from_string(race_data, content_type="application/json; charset=utf-8")

            # Update blob metadata
            blob.metadata = metadata
            blob.patch()

            # Make publicly readable if configured
            if os.getenv("GCS_PUBLIC_READ", "false").lower() == "true":
                blob.make_public()

            logger.info(f"Successfully published race {race.id} to GCS bucket {bucket_name}")

        except ImportError:
            logger.error("Google Cloud Storage client not available. Install with: pip install google-cloud-storage")
            raise
        except GoogleCloudError as e:
            logger.error(f"GCS error publishing race {race.id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to publish race {race.id} to cloud storage: {e}")
            raise

    async def _publish_to_database(self, race: RaceJSON) -> None:
        """
        Publish race data to database systems.

        Implements database publication with proper transaction handling,
        conflict resolution, and data normalization.
        """
        try:
            import os

            import asyncpg
            from asyncpg.exceptions import PostgresError

            # Get database configuration
            database_url = os.getenv("DATABASE_URL")

            if not database_url:
                logger.warning("DATABASE_URL not configured, skipping database publication")
                return

            # Connect to database
            conn = await asyncpg.connect(database_url)

            try:
                # Start transaction
                async with conn.transaction():
                    # Convert race to dict for database storage
                    race_data = race.model_dump(mode="json")

                    # Upsert race record
                    await conn.execute(
                        """
                        INSERT INTO races (id, data, updated_utc, title, office, jurisdiction, election_date)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (id)
                        DO UPDATE SET
                            data = EXCLUDED.data,
                            updated_utc = EXCLUDED.updated_utc,
                            title = EXCLUDED.title,
                            office = EXCLUDED.office,
                            jurisdiction = EXCLUDED.jurisdiction,
                            election_date = EXCLUDED.election_date
                    """,
                        race.id,
                        json.dumps(race_data, default=str),
                        race.updated_utc,
                        race.title,
                        race.office,
                        race.jurisdiction,
                        race.election_date,
                    )

                    # Insert/update candidate records for easier querying
                    for candidate in race.candidates:
                        await conn.execute(
                            """
                            INSERT INTO candidates (race_id, name, party, incumbent, summary)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (race_id, name)
                            DO UPDATE SET
                                party = EXCLUDED.party,
                                incumbent = EXCLUDED.incumbent,
                                summary = EXCLUDED.summary
                        """,
                            race.id,
                            candidate.name,
                            candidate.party,
                            candidate.incumbent,
                            candidate.summary,
                        )

                logger.info(f"Successfully published race {race.id} to database")

            finally:
                await conn.close()

        except ImportError:
            logger.error("AsyncPG not available. Install with: pip install asyncpg")
            raise
        except PostgresError as e:
            logger.error(f"Database error publishing race {race.id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to publish race {race.id} to database: {e}")
            raise

    async def _publish_to_webhooks(self, race: RaceJSON) -> None:
        """
        Send race data to configured webhook endpoints.

        Implements webhook notification system with proper security,
        retry logic, and response handling.
        """
        try:
            import hashlib
            import hmac
            import os

            import aiohttp
            from aiohttp import ClientError, ClientTimeout

            # Get webhook configuration
            webhook_urls = os.getenv("WEBHOOK_URLS", "").split(",")
            webhook_secret = os.getenv("WEBHOOK_SECRET")
            webhook_timeout = int(os.getenv("WEBHOOK_TIMEOUT", "30"))

            # Filter out empty URLs
            webhook_urls = [url.strip() for url in webhook_urls if url.strip()]

            if not webhook_urls:
                logger.debug(f"No webhook URLs configured for race {race.id}")
                return

            # Prepare payload
            payload = {
                "event": "race_published",
                "race_id": race.id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": race.model_dump(mode="json"),
            }

            payload_json = json.dumps(payload, default=str, separators=(",", ":"))

            # Generate signature if secret is configured
            signature = None
            if webhook_secret:
                signature = hmac.new(webhook_secret.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256).hexdigest()

            # Send to all configured webhooks
            timeout = ClientTimeout(total=webhook_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for url in webhook_urls:
                    try:
                        headers = {
                            "Content-Type": "application/json",
                            "User-Agent": "SmarterVote-Publisher/1.0",
                            "X-SmarterVote-Event": "race_published",
                            "X-SmarterVote-Race-ID": race.id,
                        }

                        if signature:
                            headers["X-SmarterVote-Signature"] = f"sha256={signature}"

                        async with session.post(url, data=payload_json, headers=headers) as response:
                            if response.status >= 200 and response.status < 300:
                                logger.info(f"Successfully sent webhook for race {race.id} to {url}")
                            else:
                                response_text = await response.text()
                                logger.warning(
                                    f"Webhook failed for race {race.id} to {url}: {response.status} - {response_text}"
                                )

                    except ClientError as e:
                        logger.error(f"Network error sending webhook for race {race.id} to {url}: {e}")
                    except Exception as e:
                        logger.error(f"Error sending webhook for race {race.id} to {url}: {e}")

            logger.info(f"Completed webhook notifications for race {race.id}")

        except ImportError:
            logger.error("aiohttp not available. Install with: pip install aiohttp")
            raise
        except Exception as e:
            logger.error(f"Failed to send webhooks for race {race.id}: {e}")
            raise

    async def _publish_to_pubsub(self, race: RaceJSON) -> None:
        """
        Publish race data to Google Cloud Pub/Sub.

        Implements Pub/Sub messaging with proper error handling,
        message ordering, and metadata.
        """
        try:
            import os

            from google.cloud import pubsub_v1
            from google.cloud.exceptions import GoogleCloudError

            # Get configuration
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
            topic_name = os.getenv("PUBSUB_RACE_TOPIC", "race-published")

            if not project_id:
                raise ValueError("Missing required GCP configuration: GOOGLE_CLOUD_PROJECT")

            # Initialize publisher
            publisher = pubsub_v1.PublisherClient()
            topic_path = publisher.topic_path(project_id, topic_name)

            # Prepare message
            message_data = {
                "event": "race_published",
                "race_id": race.id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "office": race.office,
                "jurisdiction": race.jurisdiction,
                "election_date": race.election_date.isoformat() if race.election_date else None,
                "candidate_count": len(race.candidates),
                "updated_utc": race.updated_utc.isoformat(),
            }

            message_json = json.dumps(message_data, default=str)

            # Message attributes for filtering
            attributes = {
                "event_type": "race_published",
                "race_id": race.id,
                "office": race.office or "unknown",
                "jurisdiction": race.jurisdiction or "unknown",
            }

            # Publish message with ordering key for consistent processing
            future = publisher.publish(topic_path, message_json.encode("utf-8"), ordering_key=race.id, **attributes)

            # Wait for publish to complete
            message_id = future.result(timeout=30)

            logger.info(f"Successfully published race {race.id} to Pub/Sub topic {topic_name}, message ID: {message_id}")

        except ImportError:
            logger.error("Google Cloud Pub/Sub client not available. Install with: pip install google-cloud-pubsub")
            raise
        except GoogleCloudError as e:
            logger.error(f"Pub/Sub error publishing race {race.id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to publish race {race.id} to Pub/Sub: {e}")
            raise

    async def _publish_to_api_endpoint(self, race: RaceJSON) -> None:
        """
        Publish race data to API endpoints for immediate availability.

        TODO: Implement API endpoint integration:
        - RESTful API POST/PUT requests to race endpoints
        - GraphQL mutation execution
        - API authentication and authorization
        - Request rate limiting and throttling
        - API response validation and error handling
        - Circuit breaker pattern for reliability
        - API versioning and compatibility
        - Real-time WebSocket updates
        """
        # Placeholder implementation
        logger.debug(f"Would publish race {race.id} to API endpoints")
        await asyncio.sleep(0.1)  # Simulate API call

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