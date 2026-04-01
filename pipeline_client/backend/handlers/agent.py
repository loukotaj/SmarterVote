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
from typing import Any, Dict, Set


def _compute_overall_progress(
    run_id: str,
    run_manager: Any,
    all_steps: list,
    step_weights: dict,
    enabled_set: Set[str],
    current_step: str | None = None,
    current_step_pct: int = 0,
) -> int:
    """Compute weighted overall progress (0-100) from step statuses."""
    run_info = run_manager.get_run(run_id)
    if not run_info:
        return 0

    # Only count enabled steps for weight denominator
    total_weight = sum(step_weights.get(s, 0) for s in all_steps if s in enabled_set)
    if total_weight == 0:
        return 0

    done_weight = 0
    partial_weight = 0
    for step_info in run_info.steps:
        w = step_weights.get(step_info.name, 0)
        if step_info.name not in enabled_set:
            continue
        if step_info.status in ("completed",):
            done_weight += w
        elif step_info.status == "running":
            # Use per-step progress or the provided current_step_pct
            pct = current_step_pct if step_info.name == current_step else (step_info.progress_pct or 0)
            partial_weight += w * pct / 100

    return min(98, int((done_weight + partial_weight) / total_weight * 100))


class AgentHandler:
    """Handler that runs the research agent and publishes RaceJSON."""

    def __init__(self, storage_backend=None):
        self.storage_backend = storage_backend

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        """Run the agent for a race_id and publish the result.

        Creates all pipeline sub-steps upfront so progress is always visible,
        then passes a step_tracker to the agent so phases report back directly.
        """
        from pipeline_client.agent.agent import run_agent
        from pipeline_client.backend.models import (
            ALL_STEPS, PipelineStep, RunStatus, STEP_LABELS, STEP_WEIGHTS,
        )

        logger = logging.getLogger("pipeline")
        race_id = payload.get("race_id")
        if not race_id:
            raise ValueError("AgentHandler: Missing 'race_id' in payload")

        cheap_mode = options.get("cheap_mode", True)
        enable_review = options.get("enable_review", True)
        enabled_steps_raw = options.get("enabled_steps")
        t0 = time.perf_counter()

        logger.info(f"Agent: researching race {race_id} (cheap_mode={cheap_mode}, review={enable_review})")

        # Resolve enabled steps: explicit list > derive from options > all
        if enabled_steps_raw:
            enabled_steps = [s for s in enabled_steps_raw if s in {e.value for e in PipelineStep}]
        else:
            enabled_steps = list(ALL_STEPS)
            if not enable_review:
                enabled_steps = [s for s in enabled_steps if s not in ("review", "iteration")]
        enabled_set = set(enabled_steps)

        # Pre-load existing data from GCS if running in cloud
        existing_data = await self._load_existing_from_gcs(race_id)

        # Get run context for broadcasting
        run_id: str | None = None
        _safe_broadcast: Any = None
        _run_manager: Any = None
        try:
            from pipeline_client.backend.pipeline_runner import _safe_broadcast
            from pipeline_client.backend.run_manager import run_manager as _run_manager
            active = next(iter(_run_manager.list_active_runs()), None)
            run_id = active.run_id if active else None
        except Exception:
            pass

        # --- Create all sub-steps upfront ---
        if run_id and _run_manager:
            for step_name in ALL_STEPS:
                try:
                    step_obj = _run_manager.add_step(run_id, step_name)
                    if step_obj:
                        step_obj.label = STEP_LABELS.get(step_name, step_name)
                        step_obj.weight = STEP_WEIGHTS.get(step_name, 0)
                        if step_name not in enabled_set:
                            _run_manager.update_step_status(run_id, step_name, RunStatus.SKIPPED)
                except Exception:
                    pass

        # --- Step tracker callbacks ---
        def _on_step_start(step: str, **_kw):
            if not run_id or not _run_manager:
                return
            try:
                _run_manager.update_step_status(run_id, step, RunStatus.RUNNING)
                label = STEP_LABELS.get(step, step)
                weight = STEP_WEIGHTS.get(step, 0)
                # Compute cumulative progress: sum of completed step weights + 0% of current
                pct = _compute_overall_progress(run_id, _run_manager, ALL_STEPS, STEP_WEIGHTS, enabled_set)
                _safe_broadcast({"type": "run_progress", "run_id": run_id, "progress": pct, "message": label})
            except Exception:
                pass

        def _on_step_complete(step: str, *, duration_ms: int = 0, **_kw):
            if not run_id or not _run_manager:
                return
            try:
                _run_manager.update_step_status(run_id, step, RunStatus.COMPLETED, duration_ms=duration_ms)
                pct = _compute_overall_progress(run_id, _run_manager, ALL_STEPS, STEP_WEIGHTS, enabled_set)
                label = STEP_LABELS.get(step, step) + " ✓"
                _safe_broadcast({"type": "run_progress", "run_id": run_id, "progress": pct, "message": label})
            except Exception:
                pass

        def _on_step_skip(step: str, **_kw):
            if not run_id or not _run_manager:
                return
            try:
                _run_manager.update_step_status(run_id, step, RunStatus.SKIPPED)
            except Exception:
                pass

        def _on_step_progress(step: str, *, pct: int = 0, message: str = "", **_kw):
            if not run_id or not _run_manager:
                return
            try:
                # Update per-step progress
                run_info = _run_manager.get_run(run_id)
                if run_info:
                    for s in run_info.steps:
                        if s.name == step:
                            s.progress_pct = pct
                            break
                overall = _compute_overall_progress(run_id, _run_manager, ALL_STEPS, STEP_WEIGHTS, enabled_set, step, pct)
                label = message or STEP_LABELS.get(step, step)
                _safe_broadcast({"type": "run_progress", "run_id": run_id, "progress": overall, "message": label})
            except Exception:
                pass

        step_tracker = {
            "start": _on_step_start,
            "complete": _on_step_complete,
            "skip": _on_step_skip,
            "progress": _on_step_progress,
        }

        # --- Log collector ---
        agent_logs: list[Dict[str, Any]] = []

        def on_log(level: str, message: str) -> None:
            log_entry = {
                "level": level,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            agent_logs.append(log_entry)
            if run_id and _run_manager:
                try:
                    _run_manager.add_run_log(run_id, log_entry)
                except Exception:
                    pass

        # Run the agent
        race_json = await run_agent(
            race_id,
            on_log=on_log,
            cheap_mode=cheap_mode,
            enable_review="review" in enabled_set,
            existing_data=existing_data,
            research_model=options.get("research_model"),
            claude_model=options.get("claude_model"),
            gemini_model=options.get("gemini_model"),
            grok_model=options.get("grok_model"),
            enabled_steps=enabled_steps,
            step_tracker=step_tracker,
        )

        # Publish to local filesystem
        published_path = await self._publish(race_id, race_json)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(f"Agent: published {race_id} to {published_path} in {duration_ms}ms")

        # Record pipeline metrics (fire-and-forget)
        try:
            from pipeline_client.backend.pipeline_metrics import get_pipeline_metrics_store
            agent_metrics = race_json.get("agent_metrics")
            rid = run_id or f"{race_id}-{int(t0)}"
            await get_pipeline_metrics_store().record_run(rid, race_id, agent_metrics, "completed")
        except Exception:
            logger.warning("Failed to record pipeline metrics", exc_info=True)

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

        # Guard against publishing a partial/corrupted LLM response
        candidates = race_json.get("candidates")
        if not isinstance(candidates, list) or len(candidates) == 0:
            raise ValueError(
                f"Refusing to publish '{race_id}': 'candidates' is missing or empty. "
                f"Top-level keys present: {list(race_json.keys())}. "
                "This usually means the LLM returned a partial object. Re-queue the race."
            )

        json_str = json.dumps(race_json, indent=2, default=str)
        with output_path.open("w", encoding="utf-8") as f:
            f.write(json_str)

        # Also publish to GCS when running in cloud environment
        await self._publish_to_gcs(race_id, json_str)

        return output_path

    async def _publish_to_gcs(self, race_id: str, json_str: str) -> None:
        """Upload race JSON to Google Cloud Storage if a GCS bucket is configured.

        Runs in both cloud and local environments — if a bucket env var is set
        (e.g. via .env), the pipeline always pushes to GCS so the deployed API
        immediately sees fresh data.
        """
        logger = logging.getLogger("pipeline")
        gcs_bucket = os.getenv("GCS_BUCKET_NAME") or os.getenv("GCS_BUCKET") or os.getenv("BUCKET_NAME")
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
        gcs_bucket = os.getenv("GCS_BUCKET_NAME") or os.getenv("GCS_BUCKET") or os.getenv("BUCKET_NAME")
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
            # Sanity-check: reject corrupt/partial files (e.g. a stray polling entry)
            if not isinstance(data.get("candidates"), list) or len(data["candidates"]) == 0:
                logger.warning(
                    f"Existing GCS file for '{race_id}' has no candidates "
                    f"(keys: {list(data.keys())}) — treating as new race"
                )
                return None
            logger.info(f"Loaded existing {race_id} from GCS for update mode")
            return data
        except ImportError:
            logger.warning("google-cloud-storage not installed; cannot load existing race from GCS")
            return None
        except Exception as e:
            logger.warning(f"Failed to load existing {race_id} from GCS: {e}")
            return None
