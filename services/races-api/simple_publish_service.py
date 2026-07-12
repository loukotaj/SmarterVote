"""
Simple publish service for races API.
This service handles reading race data from both local files and cloud storage,
providing smooth access regardless of the data source.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

from shared.models import RaceJSON

logger = logging.getLogger(__name__)

# Default TTL for in-memory GCS response cache. Set CACHE_TTL_SECONDS=0 to disable.
_DEFAULT_CACHE_TTL = 300
_SUMMARIES_BLOB = "races/summaries.json"


def _is_published_race_blob(blob_name: str) -> bool:
    return blob_name.startswith("races/") and blob_name.endswith(".json") and blob_name != _SUMMARIES_BLOB


def _normalize_summary_index(payload) -> list[dict] | None:
    if not isinstance(payload, list):
        return None
    return [item for item in payload if isinstance(item, dict) and item.get("id")]


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
        self._race_summaries_cache: Optional[Tuple[List[Dict], float]] = None
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
            logger.warning("google-cloud-storage not installed - disabling cloud mode")
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
            self._race_summaries_cache = None
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

    def _cache_get_race_summaries(self) -> Optional[List[Dict]]:
        with self._cache_lock:
            if self._race_summaries_cache is None:
                return None
            data, expiry = self._race_summaries_cache
            if time.monotonic() < expiry:
                return data
            self._race_summaries_cache = None
            return None

    def _cache_set_race_summaries(self, data: List[Dict]) -> None:
        if self.cache_ttl <= 0:
            return
        with self._cache_lock:
            self._race_summaries_cache = (data, time.monotonic() + self.cache_ttl)

    @staticmethod
    def _summary_from_race_data(race_id: str, race_data: Dict) -> Dict:
        agent_metrics = race_data.get("agent_metrics") or None
        forecast = race_data.get("forecast") or None
        return {
            "id": race_data.get("id", race_id),
            "title": race_data.get("title"),
            "office": race_data.get("office"),
            "jurisdiction": race_data.get("jurisdiction"),
            "state": race_data.get("state"),
            "contest_stage": race_data.get("contest_stage", "unknown"),
            "election_date": race_data.get("election_date", ""),
            "updated_utc": race_data.get("updated_utc", ""),
            "candidates": [
                {
                    "name": candidate.get("name", ""),
                    "party": candidate.get("party"),
                    "incumbent": candidate.get("incumbent", False),
                    "image_url": candidate.get("image_url"),
                }
                for candidate in race_data.get("candidates", [])
                if isinstance(candidate, dict)
            ],
            "agent_metrics": (
                {
                    "estimated_usd": agent_metrics.get("estimated_usd"),
                    "model": agent_metrics.get("model"),
                    "total_tokens": agent_metrics.get("total_tokens"),
                }
                if isinstance(agent_metrics, dict)
                else None
            ),
            "forecast": (
                {
                    "predicted_winner_name": forecast.get("predicted_winner_name"),
                    "predicted_winner_party": forecast.get("predicted_winner_party"),
                    "win_probability": forecast.get("win_probability"),
                    "party_probabilities": forecast.get("party_probabilities") or {},
                    "margin_estimate": forecast.get("margin_estimate"),
                    "rating": forecast.get("rating"),
                    "confidence": forecast.get("confidence"),
                    "rationale": forecast.get("rationale"),
                    "based_on_poll_count": forecast.get("based_on_poll_count", 0),
                    "generated_at": forecast.get("generated_at"),
                    "model": forecast.get("model"),
                    "source_urls": forecast.get("source_urls") or [],
                    "market_signals": forecast.get("market_signals") or [],
                }
                if isinstance(forecast, dict)
                else None
            ),
        }

    def _load_cloud_summaries_index(self, client) -> Optional[List[Dict]]:
        try:
            bucket = client.bucket(self.gcs_bucket_name)
            blob = bucket.blob(_SUMMARIES_BLOB)
            if not blob.exists():
                return None
            payload = json.loads(blob.download_as_text())
            summaries = _normalize_summary_index(payload)
            if summaries is None:
                logger.warning("Ignoring invalid cloud summaries index %s", _SUMMARIES_BLOB)
                return None
            return summaries
        except Exception as e:
            logger.warning("Error reading summaries index from GCS: %s", e, exc_info=True)
            return None

    def _load_local_summaries_index(self) -> Optional[List[Dict]]:
        index_path = self.data_directory / "summaries.json"
        if not index_path.exists():
            return None
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            summaries = _normalize_summary_index(payload)
            if summaries is None:
                logger.warning("Ignoring invalid local summaries index %s", index_path)
                return None
            return summaries
        except (json.JSONDecodeError, IOError, ValueError):
            logger.warning("Failed to parse local summaries index %s", index_path, exc_info=True)
            return None

    def get_published_races(self) -> List[str]:
        """List available race IDs.

        In cloud mode, the central summaries index is the source of truth.
        In local mode, the local summaries index is preferred and file scans are a
        development-only fallback.
        """
        cached = self._cache_get_race_list()
        if cached is not None:
            return cached

        cached_summaries = self._cache_get_race_summaries()
        if cached_summaries is not None:
            race_ids = sorted(str(summary["id"]) for summary in cached_summaries if summary.get("id"))
            self._cache_set_race_list(race_ids)
            return race_ids

        race_ids = set()
        client = self._get_gcs_client()

        if client:
            summaries = self._load_cloud_summaries_index(client)
            if summaries is not None:
                self._cache_set_race_summaries(summaries)
                result = sorted(str(summary["id"]) for summary in summaries if summary.get("id"))
                self._cache_set_race_list(result)
                return result
            logger.warning(
                "Cloud summaries index %s is unavailable; not scanning GCS blobs for published races", _SUMMARIES_BLOB
            )
            return []

        local_summaries = self._load_local_summaries_index()
        if local_summaries is not None:
            self._cache_set_race_summaries(local_summaries)
            result = sorted(str(summary["id"]) for summary in local_summaries if summary.get("id"))
            self._cache_set_race_list(result)
            return result

        # Local mode (or GCS list failed)
        if self.data_directory.exists():
            for file_path in self.data_directory.glob("*.json"):
                if file_path.name == "summaries.json":
                    continue
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "race_json" in data and "race_id" in data:
                        race_ids.add(data["race_id"])
                    else:
                        race_ids.add(file_path.stem)
                except (json.JSONDecodeError, IOError):
                    race_ids.add(file_path.stem)

        return sorted(race_ids)

    def get_race_summaries(self) -> List[Dict]:
        """Return cached race summaries.

        Cloud mode serves the central summaries index only. Local mode prefers the
        local summaries index and only scans files as a development fallback.
        """
        cached = self._cache_get_race_summaries()
        if cached is not None:
            return cached

        summaries: List[Dict] = []
        client = self._get_gcs_client()

        if client:
            indexed = self._load_cloud_summaries_index(client)
            if indexed is not None:
                self._cache_set_race_summaries(indexed)
                self._cache_set_race_list(sorted(str(summary["id"]) for summary in indexed if summary.get("id")))
                return indexed
            logger.warning(
                "Cloud summaries index %s is unavailable; not rebuilding summaries from all race blobs", _SUMMARIES_BLOB
            )
            return []

        local_indexed = self._load_local_summaries_index()
        if local_indexed is not None:
            self._cache_set_race_summaries(local_indexed)
            self._cache_set_race_list(sorted(str(summary["id"]) for summary in local_indexed if summary.get("id")))
            return local_indexed

        if self.data_directory.exists():
            for file_path in sorted(self.data_directory.glob("*.json")):
                if file_path.name == "summaries.json":
                    continue
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        race_data = json.load(f)
                    if isinstance(race_data, dict) and "race_json" in race_data and isinstance(race_data["race_json"], dict):
                        race_data = race_data["race_json"]
                    if not isinstance(race_data, dict):
                        continue
                    summaries.append(self._summary_from_race_data(file_path.stem, race_data))
                except (json.JSONDecodeError, IOError, ValueError):
                    logger.warning("Failed to parse local race summary file %s", file_path, exc_info=True)

        self._cache_set_race_summaries(summaries)
        return summaries

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
            # GCS miss - fall back to local (e.g. bootstrap data baked into image)
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

        # File not found by direct ID - scan for a pipeline-result wrapper containing this race_id
        if self.data_directory.exists():
            for candidate_path in self.data_directory.glob("*.json"):
                if candidate_path.name == "summaries.json":
                    continue
                try:
                    with open(candidate_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "race_json" in data and data.get("race_id") == race_id:
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

    def get_chamber_forecasts_data(self) -> Optional[Dict]:
        """Retrieve overall chamber-level forecasts (narratives) from GCS or local file."""
        client = self._get_gcs_client()
        if client:
            try:
                bucket = client.bucket(self.gcs_bucket_name)
                blob = bucket.blob("races/chamber_forecasts.json")
                if blob.exists():
                    return json.loads(blob.download_as_text())
            except Exception as e:
                logger.warning("Error reading chamber forecasts from GCS: %s", e)

        # Local fallback
        local_path = self.data_directory / "chamber_forecasts.json"
        if local_path.exists():
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Error reading local chamber forecasts: %s", e)
        return None
