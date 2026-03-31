"""
Simple publish service for races API.
This service handles reading race data from both local files and cloud storage,
providing smooth access regardless of the data source.
"""

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path for shared imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.models import RaceJSON

logger = logging.getLogger(__name__)

# Default TTL for in-memory GCS response cache. Set CACHE_TTL_SECONDS=0 to disable.
_DEFAULT_CACHE_TTL = 300


class SimplePublishService:
    """Service for reading published race data from multiple sources without pipeline dependencies."""

    def __init__(self, data_directory: str = "data/published/"):
        self.data_directory = Path(data_directory)
        if not self.data_directory.exists():
            self.data_directory.mkdir(parents=True, exist_ok=True)

        # Cloud storage configuration
        self.gcs_bucket_name = os.getenv("GCS_BUCKET_NAME")
        # cloud_configured = env vars are present (doesn't change after startup)
        self.cloud_configured = self._detect_cloud_environment()
        self.gcs_client = None

        if self.cloud_configured:
            self._initialize_cloud_client()

        # In-memory TTL cache so repeated requests don't hammer GCS.
        # Disabled when CACHE_TTL_SECONDS=0. Cache is cleared via clear_cache().
        self.cache_ttl = int(os.getenv("CACHE_TTL_SECONDS", str(_DEFAULT_CACHE_TTL)))
        self._race_list_cache: Optional[Tuple[List[str], float]] = None
        self._race_data_cache: Dict[str, Tuple[Dict, float]] = {}
        self._cache_lock = threading.Lock()

        logger.info(
            "Initialized SimplePublishService: local=%s, cloud_configured=%s, " "gcs_client_ok=%s, cache_ttl=%ds",
            self.data_directory,
            self.cloud_configured,
            self.gcs_client is not None,
            self.cache_ttl,
        )

    @property
    def cloud_enabled(self) -> bool:
        """True when cloud is configured AND a GCS client is available."""
        return self.cloud_configured and self.gcs_client is not None

    def _detect_cloud_environment(self) -> bool:
        """Detect if we're running in a cloud environment."""
        cloud_indicators = {
            "GOOGLE_CLOUD_PROJECT": os.getenv("GOOGLE_CLOUD_PROJECT"),
            "CLOUD_RUN_SERVICE": os.getenv("CLOUD_RUN_SERVICE"),
            "K_SERVICE": os.getenv("K_SERVICE"),
            "GAE_APPLICATION": os.getenv("GAE_APPLICATION"),
        }
        found = {k: v for k, v in cloud_indicators.items() if v}
        bucket = self.gcs_bucket_name
        logger.info("Cloud detection: indicators=%s, GCS_BUCKET_NAME=%r", found, bucket)
        result = bool(found) and bool(bucket)
        logger.info("Cloud configured: %s", result)
        return result

    def _initialize_cloud_client(self) -> None:
        """Try to initialize the GCS client.

        On a transient failure (e.g. ADC not ready at cold start) gcs_client stays
        None but cloud_configured remains True so the *next* request retries.
        Only permanently disables cloud when the library is not installed.
        """
        try:
            from google.cloud import storage

            self.gcs_client = storage.Client()
            logger.info("Initialized GCS client for bucket: %s", self.gcs_bucket_name)
        except ImportError:
            logger.warning("google-cloud-storage not installed — disabling cloud mode")
            self.cloud_configured = False  # permanent: package missing
        except Exception as e:
            logger.warning("GCS client init failed (will retry on next request): %s", e, exc_info=True)
            # Leave cloud_configured=True so the next request calls _initialize_cloud_client again

    def _get_gcs_client(self):
        """Return the GCS client, lazily re-initializing if a previous attempt failed."""
        if self.gcs_client is not None:
            return self.gcs_client
        if not self.cloud_configured:
            return None
        self._initialize_cloud_client()
        return self.gcs_client

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def clear_cache(self) -> None:
        """Discard all in-memory cached race data; next request re-fetches from GCS."""
        with self._cache_lock:
            self._race_list_cache = None
            self._race_data_cache.clear()
        logger.info("In-memory cache cleared")

    def _cache_get_race_list(self) -> Optional[List[str]]:
        with self._cache_lock:
            if self._race_list_cache is None:
                return None
            data, expiry = self._race_list_cache
            if time.monotonic() < expiry:
                return data
            self._race_list_cache = None
            return None

    def _cache_set_race_list(self, data: List[str]) -> None:
        if self.cache_ttl <= 0:
            return
        with self._cache_lock:
            self._race_list_cache = (data, time.monotonic() + self.cache_ttl)

    def _cache_get_race(self, race_id: str) -> Optional[Dict]:
        with self._cache_lock:
            entry = self._race_data_cache.get(race_id)
            if entry is None:
                return None
            data, expiry = entry
            if time.monotonic() < expiry:
                return data
            del self._race_data_cache[race_id]
            return None

    def _cache_set_race(self, race_id: str, data: Dict) -> None:
        if self.cache_ttl <= 0:
            return
        with self._cache_lock:
            self._race_data_cache[race_id] = (data, time.monotonic() + self.cache_ttl)

    def get_published_races(self) -> List[str]:
        """List available race IDs.

        In cloud mode, GCS is the source of truth.
        In local mode, scan the local published directory.
        """
        cached = self._cache_get_race_list()
        if cached is not None:
            return cached

        race_ids = set()
        client = self._get_gcs_client()

        if client:
            try:
                logger.info("Listing races from GCS bucket: %s", self.gcs_bucket_name)
                bucket = client.bucket(self.gcs_bucket_name)
                for blob in bucket.list_blobs(prefix="races/"):
                    logger.debug("  GCS blob: %s", blob.name)
                    if blob.name.endswith(".json"):
                        race_ids.add(blob.name[len("races/") : -len(".json")])
                logger.info("Listed %d races from GCS: %s", len(race_ids), sorted(race_ids))
                result = sorted(race_ids)
                self._cache_set_race_list(result)
                return result
            except Exception as e:
                logger.warning("Error listing races from GCS, falling back to local: %s", e, exc_info=True)

        # Local mode (or GCS list failed)
        if self.data_directory.exists():
            for file_path in self.data_directory.glob("*.json"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if "race_json" in data and "race_id" in data:
                        race_ids.add(data["race_id"])
                    else:
                        race_ids.add(file_path.stem)
                except (json.JSONDecodeError, IOError):
                    race_ids.add(file_path.stem)

        return sorted(race_ids)

    def get_race_data(self, race_id: str) -> Optional[Dict]:
        """Retrieve race data by ID from local files or cloud storage.

        Priority:
        - Cloud mode: GCS first (TTL-cached), local as fallback
        - Local mode: local files only
        """
        cached = self._cache_get_race(race_id)
        if cached is not None:
            return cached

        client = self._get_gcs_client()
        if client:
            data = self._get_race_data_cloud(race_id, client)
            if data:
                self._cache_set_race(race_id, data)
                return data
            # GCS miss — fall back to local (e.g. bootstrap data baked into image)
            logger.debug("GCS miss for %s, falling back to local", race_id)

        return self._get_race_data_local(race_id)

    def _get_race_data_local(self, race_id: str) -> Optional[Dict]:
        """Get race data from local file."""
        file_path = self.data_directory / f"{race_id}.json"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Unwrap pipeline-result wrapper files
                if "race_json" in data:
                    data = data["race_json"]
                logger.debug(f"Loaded race {race_id} from local file")
                return data
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error reading local file for race {race_id}: {e}")
                return None

        # File not found by direct ID — scan for a pipeline-result wrapper containing this race_id
        if self.data_directory.exists():
            for candidate_path in self.data_directory.glob("*.json"):
                try:
                    with open(candidate_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if "race_json" in data and data.get("race_id") == race_id:
                        logger.debug(f"Loaded race {race_id} from wrapper file {candidate_path.name}")
                        return data["race_json"]
                except (json.JSONDecodeError, IOError):
                    continue

        return None

    def _get_race_data_cloud(self, race_id: str, client=None) -> Optional[Dict]:
        """Get race data from cloud storage."""
        if client is None:
            client = self._get_gcs_client()
        if not client:
            return None

        try:
            bucket = client.bucket(self.gcs_bucket_name)
            blob_name = f"races/{race_id}.json"
            blob = bucket.blob(blob_name)

            if not blob.exists():
                return None

            data_str = blob.download_as_text()
            data = json.loads(data_str)
            logger.debug("Loaded race %s from cloud storage", race_id)
            return data

        except Exception as e:
            logger.warning("Error reading from cloud storage for race %s: %s", race_id, e)
            return None

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
