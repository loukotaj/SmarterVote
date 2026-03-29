"""Agent handler: single-step agent-based candidate research.

Wraps the research agent as a pipeline step handler so it integrates with
the pipeline_client execution engine, storage, and logging.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

# Maps log message patterns → (progress %, label).
# Checked in order — first match wins.
_PROGRESS_PATTERNS: list[tuple[re.Pattern, int, str]] = [
    (re.compile(r"Phase 1/3|Phase 1b/3|Discovering race"),         5,  "Discovering race & candidates..."),
    (re.compile(r"Verifying and resolving candidate image"),        10, "Verifying candidate images..."),
    (re.compile(r"Phase 2/3|Researching issues"),                   15, "Researching issues..."),
    (re.compile(r"Issue group 1/"),                                 20, "Issues: group 1/6..."),
    (re.compile(r"Issue group 2/"),                                 30, "Issues: group 2/6..."),
    (re.compile(r"Issue group 3/"),                                 40, "Issues: group 3/6..."),
    (re.compile(r"Issue group 4/"),                                 50, "Issues: group 4/6..."),
    (re.compile(r"Issue group 5/"),                                 58, "Issues: group 5/6..."),
    (re.compile(r"Issue group 6/"),                                 65, "Issues: group 6/6..."),
    (re.compile(r"Phase 3/3|Refining and validating"),             72, "Refining & validating..."),
    (re.compile(r"Phase 4:|Sending to review agents"),             82, "Sending to review agents..."),
    (re.compile(r"Phase 5:|Iterating on review feedback"),         90, "Iterating on review feedback..."),
    (re.compile(r"✅ Agent finished|Agent finished"),              98, "Finalising..."),
]


def _detect_progress(message: str) -> tuple[int, str] | None:
    for pattern, pct, label in _PROGRESS_PATTERNS:
        if pattern.search(message):
            return pct, label
    return None


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

        # Collect logs from the agent and broadcast progress via WebSocket
        agent_logs: list[Dict[str, Any]] = []
        run_id: str | None = None
        try:
            from pipeline_client.backend.pipeline_runner import _safe_broadcast
            from pipeline_client.backend.run_manager import run_manager
            active = next(iter(run_manager.list_active_runs()), None)
            run_id = active.run_id if active else None
        except Exception:
            pass

        def on_log(level: str, message: str) -> None:
            agent_logs.append(
                {
                    "level": level,
                    "message": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            progress_hit = _detect_progress(message)
            if progress_hit and run_id:
                pct, label = progress_hit
                try:
                    _safe_broadcast({"type": "run_progress", "run_id": run_id, "progress": pct, "message": label})
                except Exception:
                    pass


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
