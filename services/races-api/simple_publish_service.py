"""
Simple publish service for races API.
This service handles reading race data from both local files and cloud storage,
providing smooth access regardless of the data source.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path for shared imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.models import RaceJSON

logger = logging.getLogger(__name__)


class SimplePublishService:
    """Service for reading published race data from multiple sources without pipeline dependencies."""

    def __init__(self, data_directory: str = "data/published/"):
        self.data_directory = Path(data_directory)
        if not self.data_directory.exists():
            self.data_directory.mkdir(parents=True, exist_ok=True)

        # Cloud storage configuration
        self.cloud_enabled = self._detect_cloud_environment()
        self.gcs_bucket_name = os.getenv("GCS_BUCKET_NAME")
        self.gcs_client = None

        if self.cloud_enabled:
            self._initialize_cloud_client()

        logger.info(f"Initialized SimplePublishService: local={self.data_directory}, cloud_enabled={self.cloud_enabled}")

    def _detect_cloud_environment(self) -> bool:
        """Detect if we're running in a cloud environment."""
        cloud_indicators = [
            os.getenv("GOOGLE_CLOUD_PROJECT"),
            os.getenv("CLOUD_RUN_SERVICE"),
            os.getenv("K_SERVICE"),
            os.getenv("GAE_APPLICATION"),
        ]
        return any(cloud_indicators) and os.getenv("GCS_BUCKET_NAME")

    def _initialize_cloud_client(self):
        """Initialize Google Cloud Storage client if available."""
        try:
            from google.cloud import storage

            self.gcs_client = storage.Client()
            logger.info(f"Initialized GCS client for bucket: {self.gcs_bucket_name}")
        except ImportError:
            logger.warning("Google Cloud Storage client not available")
            self.cloud_enabled = False
        except Exception as e:
            logger.warning(f"Failed to initialize GCS client: {e}")
            self.cloud_enabled = False

    def get_published_races(self) -> List[str]:
        """List available race IDs from both local files and cloud storage."""
        race_ids = set()

        # Get from local files
        if self.data_directory.exists():
            for file_path in self.data_directory.glob("*.json"):
                race_id = file_path.stem
                race_ids.add(race_id)

        # Get from cloud storage if available
        if self.cloud_enabled and self.gcs_client:
            try:
                bucket = self.gcs_client.bucket(self.gcs_bucket_name)
                blobs = bucket.list_blobs(prefix="races/")

                for blob in blobs:
                    if blob.name.endswith(".json"):
                        # Extract race ID from "races/race-id.json"
                        race_id = blob.name.replace("races/", "").replace(".json", "")
                        race_ids.add(race_id)

                logger.info(f"Found {len(race_ids)} total races across local and cloud sources")
            except Exception as e:
                logger.warning(f"Error listing races from cloud storage: {e}")

        return sorted(list(race_ids))

    def get_race_data(self, race_id: str) -> Optional[Dict]:
        """Retrieve race data by ID from local files or cloud storage."""
        # Try local file first (faster)
        data = self._get_race_data_local(race_id)
        if data:
            return data

        # Fall back to cloud storage
        if self.cloud_enabled:
            data = self._get_race_data_cloud(race_id)
            if data:
                # Cache locally for future requests
                self._cache_race_data_locally(race_id, data)
                return data

        return None

    def _get_race_data_local(self, race_id: str) -> Optional[Dict]:
        """Get race data from local file."""
        file_path = self.data_directory / f"{race_id}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.debug(f"Loaded race {race_id} from local file")
            return data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Error reading local file for race {race_id}: {e}")
            return None

    def _get_race_data_cloud(self, race_id: str) -> Optional[Dict]:
        """Get race data from cloud storage."""
        if not self.cloud_enabled or not self.gcs_client:
            return None

        try:
            bucket = self.gcs_client.bucket(self.gcs_bucket_name)
            blob_name = f"races/{race_id}.json"
            blob = bucket.blob(blob_name)

            if not blob.exists():
                return None

            data_str = blob.download_as_text()
            data = json.loads(data_str)
            logger.debug(f"Loaded race {race_id} from cloud storage")
            return data

        except Exception as e:
            logger.warning(f"Error reading from cloud storage for race {race_id}: {e}")
            return None

    def _cache_race_data_locally(self, race_id: str, data: Dict):
        """Cache race data locally for faster future access."""
        try:
            file_path = self.data_directory / f"{race_id}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            logger.debug(f"Cached race {race_id} locally")
        except Exception as e:
            logger.warning(f"Failed to cache race {race_id} locally: {e}")

    def get_race(self, race_id: str) -> Optional[RaceJSON]:
        """Retrieve race data as RaceJSON model."""
        data = self.get_race_data(race_id)
        if not data:
            return None

        try:
            return RaceJSON(**data)
        except Exception as e:
            logger.warning(f"Error creating RaceJSON for race {race_id}: {e}")
            return None
