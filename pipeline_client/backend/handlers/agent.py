"""Agent handler: single-step agent-based candidate research.

Wraps the research agent as a pipeline step handler so it integrates with
the pipeline_client execution engine, storage, and logging.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class AgentHandler:
    """Handler that runs the research agent and publishes RaceJSON."""

    def __init__(self, storage_backend=None):
        self.storage_backend = storage_backend

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        """Run the agent for a race_id and publish the result.

        Payload expected:
            - race_id: str (e.g. "mo-senate-2024")

        Options:
            - cheap_mode: bool (default True, uses gpt-5.4-mini in cheap, gpt-5.4 in full)
            - enable_review: bool (default False, send to Claude/Gemini/Grok)
            - research_model: str (override OpenAI research model)
            - claude_model: str (override Claude review model)
            - gemini_model: str (override Gemini review model)
            - grok_model: str (override Grok review model)

        Returns:
            dict with race_id, race_json, published_path, duration_ms
        """
        from pipeline_client.agent.agent import run_agent

        logger = logging.getLogger("pipeline")
        race_id = payload.get("race_id")
        if not race_id:
            raise ValueError("AgentHandler: Missing 'race_id' in payload")

        cheap_mode = options.get("cheap_mode", True)
        enable_review = options.get("enable_review", True)
        t0 = time.perf_counter()

        logger.info(f"Agent: researching race {race_id} (cheap_mode={cheap_mode}, review={enable_review})")

        # Pre-load existing data from GCS if running in cloud (container filesystem
        # may be ephemeral, so _load_existing() won't find local files from previous runs).
        existing_data = await self._load_existing_from_gcs(race_id)

        # Collect logs from the agent
        agent_logs: list[Dict[str, Any]] = []

        def on_log(level: str, message: str) -> None:
            agent_logs.append(
                {
                    "level": level,
                    "message": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        # Run the agent
        race_json = await run_agent(
            race_id,
            on_log=on_log,
            cheap_mode=cheap_mode,
            enable_review=enable_review,
            existing_data=existing_data,
            research_model=options.get("research_model"),
            claude_model=options.get("claude_model"),
            gemini_model=options.get("gemini_model"),
            grok_model=options.get("grok_model"),
        )

        # Publish to local filesystem
        published_path = await self._publish(race_id, race_json)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(f"Agent: published {race_id} to {published_path} in {duration_ms}ms")

        return {
            "race_id": race_id,
            "race_json": race_json,
            "published_path": str(published_path),
            "duration_ms": duration_ms,
            "agent_logs": agent_logs,
            "status": "published",
        }

    async def _publish(self, race_id: str, race_json: Dict[str, Any]) -> Path:
        """Write RaceJSON to the published data directory and optionally to GCS."""
        logger = logging.getLogger("pipeline")
        published_dir = Path(__file__).resolve().parents[3] / "data" / "published"
        published_dir.mkdir(parents=True, exist_ok=True)

        output_path = published_dir / f"{race_id}.json"

        # Backup existing file if present
        if output_path.exists():
            backup_path = output_path.with_suffix(
                f".json.backup.{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            )
            output_path.rename(backup_path)

        json_str = json.dumps(race_json, indent=2, default=str)
        with output_path.open("w", encoding="utf-8") as f:
            f.write(json_str)

        # Also publish to GCS when running in cloud environment
        await self._publish_to_gcs(race_id, json_str)

        return output_path

    async def _publish_to_gcs(self, race_id: str, json_str: str) -> None:
        """Upload race JSON to Google Cloud Storage if GCS_BUCKET_NAME is configured.

        Runs in both cloud and local environments — if GCS_BUCKET_NAME is set in
        the environment (e.g. via .env), the pipeline always pushes to GCS so the
        deployed API immediately sees fresh data.
        """
        logger = logging.getLogger("pipeline")
        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        if not gcs_bucket:
            return

        try:
            from google.cloud import storage  # type: ignore

            client = storage.Client()
            bucket = client.bucket(gcs_bucket)
            blob = bucket.blob(f"races/{race_id}.json")
            blob.upload_from_string(json_str, content_type="application/json")
            logger.info(f"Published {race_id} to GCS: gs://{gcs_bucket}/races/{race_id}.json")
        except ImportError:
            logger.warning("google-cloud-storage not installed; skipping GCS upload")
        except Exception as e:
            logger.warning(f"Failed to upload {race_id} to GCS: {e}")

    async def _load_existing_from_gcs(self, race_id: str) -> Dict[str, Any] | None:
        """Load existing race data from GCS so deployed containers use update mode.

        On Cloud Run the local filesystem is ephemeral, so ``_load_existing``
        in the agent module won't find previous runs. This method fetches the
        current published version from GCS to hand to the agent as
        ``existing_data``, ensuring the agent enters update mode rather than
        creating a duplicate fresh profile.  Returns *None* when GCS is not
        configured or the race doesn't exist yet.
        """
        logger = logging.getLogger("pipeline")
        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        if not gcs_bucket:
            return None

        try:
            from google.cloud import storage  # type: ignore

            client = storage.Client()
            bucket = client.bucket(gcs_bucket)
            blob = bucket.blob(f"races/{race_id}.json")
            if not blob.exists():
                return None
            data = json.loads(blob.download_as_text())
            logger.info(f"Loaded existing {race_id} from GCS for update mode")
            return data
        except ImportError:
            logger.warning("google-cloud-storage not installed; cannot load existing race from GCS")
            return None
        except Exception as e:
            logger.warning(f"Failed to load existing {race_id} from GCS: {e}")
            return None


class IterateHandler:
    """Handler that runs a review-feedback iteration pass on an existing profile."""

    def __init__(self, storage_backend=None):
        self.storage_backend = storage_backend

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        """Run iteration for a race_id using review feedback.

        Payload expected:
            - race_id: str
            - review_flags: list (optional, uses stored reviews if missing)

        Returns:
            dict with race_id, race_json, published_path, duration_ms
        """
        from pipeline_client.agent.agent import run_iteration

        logger = logging.getLogger("pipeline")
        race_id = payload.get("race_id")
        if not race_id:
            raise ValueError("IterateHandler: Missing 'race_id' in payload")

        cheap_mode = options.get("cheap_mode", True)
        # Iteration always re-runs review to validate improvements
        enable_review = True
        review_flags = payload.get("review_flags")
        t0 = time.perf_counter()

        logger.info(f"Iterate: improving race {race_id} (cheap_mode={cheap_mode}, review={enable_review})")

        # Load existing data from GCS if in cloud
        existing_data = await AgentHandler(self.storage_backend)._load_existing_from_gcs(race_id)

        agent_logs: list[Dict[str, Any]] = []

        def on_log(level: str, message: str) -> None:
            agent_logs.append({
                "level": level,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        race_json = await run_iteration(
            race_id,
            on_log=on_log,
            cheap_mode=cheap_mode,
            enable_review=enable_review,
            existing_data=existing_data,
            review_flags=review_flags,
            research_model=options.get("research_model"),
            claude_model=options.get("claude_model"),
            gemini_model=options.get("gemini_model"),
            grok_model=options.get("grok_model"),
        )

        # Publish (reuse AgentHandler's publish method)
        agent_handler = AgentHandler(self.storage_backend)
        published_path = await agent_handler._publish(race_id, race_json)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(f"Iterate: published {race_id} to {published_path} in {duration_ms}ms")

        return {
            "race_id": race_id,
            "race_json": race_json,
            "published_path": str(published_path),
            "duration_ms": duration_ms,
            "agent_logs": agent_logs,
            "status": "published",
            "iteration_notes": race_json.get("iteration_notes", []),
        }
