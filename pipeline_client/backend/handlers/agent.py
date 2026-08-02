"""Agent handler: single-step agent-based candidate research.

Wraps the research agent as a pipeline step handler so it integrates with
the pipeline_client execution engine, storage, and logging.
"""

import json
import logging
import os
import re
import shutil
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set

from pipeline_client.logging_utils import sanitize_log_message_with_metadata
from shared.config import GCS_CHECKPOINTS_PREFIX, local_paths
from shared.pipeline_config import RetentionConfig


class HandoffTriggered(Exception):
    """Raised after the agent checkpoints work into a continuation queue item.

    The shared queue processor follows these continuations in-process for both
    one-shot Cloud Run Jobs and the long-lived local Docker worker.
    """

    def __init__(self, continuation_item_id: str, remaining_steps: List[str], continuation_run_id: str | None = None):
        self.continuation_item_id = continuation_item_id
        self.remaining_steps = remaining_steps
        self.continuation_run_id = continuation_run_id
        super().__init__(f"Handoff to continuation item {continuation_item_id}")


class HandoffFailed(RuntimeError):
    """Raised when a deadline handoff cannot safely create its continuation item."""


class AgentCancelled(Exception):
    """Raised when a running queue item has been cancelled by an admin."""


# Default deadline: 55 minutes (gives 5-min buffer before CF's 60-min hard limit)
DEFAULT_DEADLINE_SECONDS: int = 3300
_PLACEHOLDER_CANDIDATE_NAMES = {"", "unknown", "tbd", "to be determined", "n/a", "na", "none"}


def _candidate_name(candidate: Any) -> str:
    if not isinstance(candidate, dict):
        return ""
    return str(candidate.get("name") or "").strip()


def _is_placeholder_candidate_name(name: str) -> bool:
    return name.strip().lower() in _PLACEHOLDER_CANDIDATE_NAMES


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

    def _get_storage_client(self):
        """Return a GCS storage client without importing FastAPI app modules."""
        from pipeline_client.backend.gcs_client import get_gcs_client

        return get_gcs_client()

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        """Run the agent for a race_id and publish the result.

        Creates all pipeline sub-steps upfront so progress is always visible,
        then passes a step_tracker to the agent so phases report back directly.
        """
        from pipeline_client.agent.agent import run_agent
        from pipeline_client.agent.phases import PipelineWorkRemaining
        from pipeline_client.agent.run_budget import RunBudget, RunBudgetExceeded
        from pipeline_client.backend.models import ALL_STEPS, STEP_LABELS, STEP_WEIGHTS, PipelineStep, RunStatus

        logger = logging.getLogger("pipeline")
        race_id = payload.get("race_id")
        if not race_id:
            raise ValueError("AgentHandler: Missing 'race_id' in payload")

        cheap_mode = options.get("cheap_mode", True)
        enabled_steps_raw = options.get("enabled_steps")
        queue_item_id = options.get("queue_item_id")
        t0 = time.perf_counter()

        logger.info(f"Agent: researching race {race_id} (cheap_mode={cheap_mode})")

        # Pre-load existing data. Continuation runs receive checkpoint data from
        # the Cloud Function payload; that is more precise than drafts/races GCS.
        # It must win over force_fresh, otherwise fresh runs restart from
        # discovery after every deadline handoff instead of resuming.
        if isinstance(payload.get("existing_data"), dict):
            existing_data = payload["existing_data"]
            logger.info("Agent: loaded checkpoint payload for continuation %s", race_id)
        elif options.get("force_fresh"):
            existing_data = {}
        else:
            existing_data = await self._load_existing_from_gcs(
                race_id, baseline_source=options.get("baseline_source", "latest")
            )

        # Resolve enabled steps only after baseline loading so an unspecified
        # step list can distinguish a genuine update from new research.
        if enabled_steps_raw:
            enabled_steps = [s for s in enabled_steps_raw if s in {e.value for e in PipelineStep}]
        elif existing_data:
            from shared.pipeline_config import DEFAULT_UPDATE_PIPELINE_STEPS

            enabled_steps = list(DEFAULT_UPDATE_PIPELINE_STEPS)
            options["enabled_steps"] = enabled_steps
            logger.info("Agent: using low-cost update steps (issue research and review are opt-in)")
        else:
            enabled_steps = list(ALL_STEPS)
        enabled_set = set(enabled_steps)
        all_enabled_steps_raw = options.get("all_enabled_steps")
        if all_enabled_steps_raw:
            all_enabled_steps = [s for s in all_enabled_steps_raw if s in {e.value for e in PipelineStep}]
        elif options.get("is_continuation"):
            all_enabled_steps = list(ALL_STEPS)
        else:
            all_enabled_steps = list(enabled_steps)
        all_enabled_set = set(all_enabled_steps)

        configured_baseline_names = options.get("verified_baseline_candidate_names")
        if isinstance(configured_baseline_names, list):
            verified_baseline_candidate_names = {
                str(name).strip().casefold() for name in configured_baseline_names if str(name).strip()
            }
        else:
            verified_baseline_candidate_names = {
                _candidate_name(candidate).casefold()
                for candidate in (existing_data or {}).get("candidates", [])
                if _candidate_name(candidate)
            }
            options["verified_baseline_candidate_names"] = sorted(verified_baseline_candidate_names)

        # Deadline for Cloud Function handoff.  Callers (CF entry point) can
        # inject a tighter deadline via options; default is 55 min from now.
        deadline_at: float = options.get("deadline_at", time.time() + DEFAULT_DEADLINE_SECONDS)
        run_budget = RunBudget(
            deadline_at=deadline_at,
            checkpoint_buffer_seconds=float(options.get("checkpoint_buffer_seconds", 15.0)),
        )

        # Firestore logger (fire-and-forget; no-ops locally when Firestore is absent)
        from pipeline_client.backend.firestore_logger import FirestoreLogger

        # Get run context for broadcasting
        # Resolve run_id from options first so Firestore logging still works
        # even if optional local pipeline imports fail in Cloud Function.
        run_id: str | None = options.get("run_id")
        _safe_broadcast: Any = None
        _run_manager: Any = None
        try:
            from pipeline_client.backend.pipeline_runner import _safe_broadcast
            from pipeline_client.backend.run_manager import run_manager as _run_manager

            if not run_id:
                # Fallback: pick the first active run (legacy path)
                active = next(iter(_run_manager.list_active_runs()), None)
                run_id = active.run_id if active else None
        except Exception as _e:
            logger.debug("Failed to resolve run context: %s", _e)

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
                except Exception as _e:
                    logger.debug("Failed to initialise step '%s': %s", step_name, _e)

        # Initialise Firestore logger once we have (or might have) a run_id.
        # We create it speculatively here; it no-ops gracefully if run_id is None.
        _fs_logger: Any = None  # set after run_id is resolved below

        # Compute completed steps so far (used for remaining_steps on handoff)
        _completed_steps = [s for s in options.get("completed_steps", []) if s in all_enabled_set]
        if options.get("is_continuation"):
            for step in all_enabled_steps:
                if step not in enabled_set and step not in _completed_steps:
                    _completed_steps.append(step)
        _handoff_started = False
        _current_step: str | None = None

        def _fallback_progress(current_step: str | None = None, current_step_pct: int = 0) -> int:
            """Compute weighted progress without run_manager state."""
            total_weight = sum(STEP_WEIGHTS.get(s, 0) for s in ALL_STEPS if s in all_enabled_set)
            if total_weight <= 0:
                return 0

            done_weight = sum(STEP_WEIGHTS.get(s, 0) for s in _completed_steps if s in all_enabled_set)
            partial_weight_pct = 0
            if current_step and current_step in all_enabled_set and current_step not in _completed_steps:
                partial_weight_pct = STEP_WEIGHTS.get(current_step, 0) * max(0, min(current_step_pct, 100))

            return min(98, (done_weight * 100 + partial_weight_pct) // total_weight)

        def _overall_progress(current_step: str | None = None, current_step_pct: int = 0) -> int:
            """Use local run state when present; Cloud Functions rely on checkpoint state."""
            local_runs = getattr(_run_manager, "active_runs", {}) if _run_manager else {}
            if run_id in local_runs:
                return _compute_overall_progress(
                    run_id,
                    _run_manager,
                    ALL_STEPS,
                    STEP_WEIGHTS,
                    enabled_set,
                    current_step,
                    current_step_pct,
                )
            return _fallback_progress(current_step, current_step_pct)

        def _broadcast_progress(pct: int, label: str) -> None:
            if run_id and _safe_broadcast:
                _safe_broadcast({"type": "run_progress", "run_id": run_id, "progress": pct, "message": label})

        def _raise_if_cancelled() -> None:
            if not queue_item_id:
                return
            try:
                from pipeline_client.backend.firestore_logger import _get_db

                db = _get_db()
                if db is None:
                    return
                doc = db.collection("pipeline_queue").document(queue_item_id).get()
                if doc.exists and (doc.to_dict() or {}).get("status") == "cancelled":
                    raise AgentCancelled(f"Run {run_id or ''} for {race_id} was cancelled")
            except AgentCancelled:
                raise
            except Exception as exc:
                logger.debug("Cancellation check failed for queue item %s: %s", queue_item_id, exc)

        def _maybe_handoff(reason: str, *, step: str | None = None, pct: int = 0, force: bool = False) -> None:
            """Handoff when the deadline has passed. Safe to call from deep callbacks."""
            nonlocal _handoff_started
            if _handoff_started or not run_id or (not force and time.time() <= deadline_at):
                return
            _raise_if_cancelled()
            active_step = step or _current_step
            remaining = [s for s in enabled_steps if s not in _completed_steps]
            if not remaining:
                return
            _handoff_started = True
            current_pct = _fallback_progress(active_step, pct)
            logger.warning(
                "Deadline exceeded %s%s; handing off to continuation. Remaining steps: %s",
                reason,
                f" during step '{active_step}'" if active_step else "",
                remaining,
            )
            _trigger_handoff(run_id, race_id, remaining, current_pct)

        # --- Step tracker callbacks ---
        step_start_metrics = {}

        def _on_step_start(step: str, **_kw):
            nonlocal _current_step
            _raise_if_cancelled()
            if not run_id:
                return
            try:
                from pipeline_client.agent.cost import _cost_ctx

                cost_snapshot = _cost_ctx.get()
                if cost_snapshot:
                    step_start_metrics[step] = {
                        "prompt_tokens": cost_snapshot.get("prompt_tokens", 0),
                        "completion_tokens": cost_snapshot.get("completion_tokens", 0),
                        "provider_cost_usd": cost_snapshot.get("provider_cost_usd", 0.0),
                        "model_breakdown": {m: dict(counts) for m, counts in cost_snapshot.get("model_breakdown", {}).items()},
                    }
                else:
                    step_start_metrics[step] = {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "provider_cost_usd": 0.0,
                        "model_breakdown": {},
                    }

                _current_step = step
                if _run_manager:
                    _run_manager.update_step_status(run_id, step, RunStatus.RUNNING)
                label = STEP_LABELS.get(step, step)
                pct = _overall_progress(step, 1)
                _broadcast_progress(pct, label)
                if _fs_logger:
                    remaining = [s for s in enabled_steps if s not in _completed_steps]
                    _fs_logger.update_progress(
                        pct,
                        current_step=step,
                        current_step_progress=0,
                        progress_message=label,
                        remaining_steps=remaining,
                    )
                    _fs_logger.log(
                        "info",
                        f"Step started: {label}",
                        step=step,
                        race_id=race_id,
                        extra={
                            "event": "step_started",
                            "overall_progress": pct,
                            "remaining_steps": remaining,
                        }
                        if debug_mode
                        else None,
                    )
            except (HandoffTriggered, HandoffFailed):
                raise
            except Exception as _e:
                logger.debug("_on_step_start tracking failed for '%s': %s", step, _e)

        def _on_step_complete(step: str, *, duration_ms: int = 0, **_kw):
            nonlocal _completed_steps, _current_step
            if not run_id:
                return
            try:
                latest_race_json = _kw.get("race_json")
                if isinstance(latest_race_json, dict):
                    race_json_holder[0] = latest_race_json

                prompt_tokens = None
                completion_tokens = None
                estimated_usd = None

                from pipeline_client.agent.cost import _cost_ctx, estimate_cost

                cost_snapshot = _cost_ctx.get()
                if cost_snapshot:
                    start = step_start_metrics.get(
                        step,
                        {
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "model_breakdown": {},
                        },
                    )
                    prompt_tokens = max(0, cost_snapshot.get("prompt_tokens", 0) - start["prompt_tokens"])
                    completion_tokens = max(0, cost_snapshot.get("completion_tokens", 0) - start["completion_tokens"])

                    estimated_usd = 0.0
                    curr_breakdown = cost_snapshot.get("model_breakdown", {})
                    start_breakdown = start.get("model_breakdown", {})
                    for model, curr_counts in curr_breakdown.items():
                        start_counts = start_breakdown.get(model, {"prompt_tokens": 0, "completion_tokens": 0})
                        m_prompt = max(0, curr_counts.get("prompt_tokens", 0) - start_counts.get("prompt_tokens", 0))
                        m_completion = max(
                            0, curr_counts.get("completion_tokens", 0) - start_counts.get("completion_tokens", 0)
                        )
                        if m_prompt > 0 or m_completion > 0:
                            estimated_usd += estimate_cost(model, m_prompt, m_completion)

                step_failure_reasons: list = []
                if isinstance(latest_race_json, dict):
                    from shared.run_health import get_step_failures

                    step_failure_reasons = [f.reason for f in get_step_failures(latest_race_json) if f.step == step]

                if _run_manager:
                    _run_manager.update_step_status(
                        run_id,
                        step,
                        RunStatus.COMPLETED,
                        duration_ms=duration_ms,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        estimated_usd=estimated_usd,
                        failure_reasons=step_failure_reasons,
                    )
                _completed_steps.append(step)
                pct = _overall_progress()
                label = STEP_LABELS.get(step, step) + " complete"
                _broadcast_progress(pct, label)

                # --- Checkpoint / handoff check ---
                # Must happen AFTER the step is marked complete so the saved
                # race_json is the latest version.
                _maybe_handoff("after step completion", step=step, pct=100)

                if _fs_logger:
                    remaining = [s for s in enabled_steps if s not in _completed_steps]
                    _fs_logger.update_progress(
                        pct,
                        current_step=step,
                        current_step_progress=100,
                        progress_message=label,
                        remaining_steps=remaining,
                    )
                    _fs_logger.log(
                        "info",
                        f"Step completed in {duration_ms}ms: {label}",
                        step=step,
                        race_id=race_id,
                        extra={
                            "event": "step_completed",
                            "duration_ms": duration_ms,
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "estimated_usd": estimated_usd,
                            "overall_progress": pct,
                            "remaining_steps": remaining,
                        }
                        if debug_mode
                        else None,
                    )
                if _current_step == step:
                    _current_step = None
            except (HandoffTriggered, HandoffFailed):
                raise
            except Exception as _e:
                logger.debug("_on_step_complete tracking failed for '%s': %s", step, _e)

        def _on_step_skip(step: str, **_kw):
            nonlocal _current_step
            if not run_id:
                return
            try:
                if _run_manager:
                    _run_manager.update_step_status(run_id, step, RunStatus.SKIPPED)
                if _fs_logger:
                    _fs_logger.log(
                        "info",
                        f"Step skipped: {step}",
                        step=step,
                        race_id=race_id,
                        extra={"event": "step_skipped"} if debug_mode else None,
                    )
                if _current_step == step:
                    _current_step = None
            except Exception as _e:
                logger.debug("_on_step_skip tracking failed for '%s': %s", step, _e)

        def _on_step_progress(step: str, *, pct: int = 0, message: str = "", **_kw):
            nonlocal _current_step
            _raise_if_cancelled()
            if not run_id:
                return
            try:
                _current_step = step
                latest_race_json = _kw.get("race_json")
                if isinstance(latest_race_json, dict):
                    race_json_holder[0] = latest_race_json
                _maybe_handoff("during progress callback", step=step, pct=pct)

                # Update per-step progress
                if _run_manager:
                    run_info = _run_manager.get_run(run_id)
                    if run_info:
                        for s in run_info.steps:
                            if s.name == step:
                                s.progress_pct = pct
                                break
                overall = _overall_progress(step, pct)
                label = message or STEP_LABELS.get(step, step)
                _broadcast_progress(overall, label)
                if _fs_logger:
                    remaining = [s for s in enabled_steps if s not in _completed_steps]
                    _fs_logger.update_progress(
                        overall,
                        current_step=step,
                        current_step_progress=pct,
                        progress_message=label,
                        remaining_steps=remaining,
                    )
                    if debug_mode:
                        bucket = max(0, min(10, int(pct) // 10))
                        if debug_progress_buckets.get(step) != bucket:
                            debug_progress_buckets[step] = bucket
                            _fs_logger.log(
                                "debug",
                                f"Step progress {pct}%: {label}",
                                step=step,
                                race_id=race_id,
                                extra={
                                    "event": "step_progress",
                                    "step_progress": pct,
                                    "overall_progress": overall,
                                    "remaining_steps": remaining,
                                },
                            )
            except (HandoffTriggered, HandoffFailed):
                raise
            except Exception as _e:
                logger.debug("_on_step_progress tracking failed for '%s': %s", step, _e)

        step_tracker = {
            "start": _on_step_start,
            "complete": _on_step_complete,
            "skip": _on_step_skip,
            "progress": _on_step_progress,
        }

        # Initialise FirestoreLogger now that run_id is resolved
        if run_id:
            _fs_logger = FirestoreLogger(run_id)
        else:
            _fs_logger = None

        def _trigger_handoff(current_run_id: str, current_race_id: str, remaining: List[str], current_pct: int) -> None:
            """Save checkpoint to GCS, write continuation queue item, raise HandoffTriggered."""
            from pipeline_client.backend.firestore_logger import FirestoreLogger as _FL
            from pipeline_client.backend.settings import settings

            item_id = uuid.uuid4().hex[:8]
            continuation_run_id = current_run_id
            checkpoint_gcs_path: Optional[str] = None

            # Try to save the latest race_json to GCS as a checkpoint
            # (race_json is captured from the enclosing scope at handoff time)
            try:
                gcs_bucket = settings.gcs_bucket
                if gcs_bucket and race_json_holder:
                    client = self._get_storage_client()
                    if client:
                        path = f"{GCS_CHECKPOINTS_PREFIX}/{current_run_id}.json"
                        client.bucket(gcs_bucket).blob(path).upload_from_string(
                            json.dumps(race_json_holder[0], default=str),
                            content_type="application/json",
                        )
                        checkpoint_gcs_path = f"gs://{gcs_bucket}/{path}"
                        logger.info("Checkpoint saved to %s", checkpoint_gcs_path)
            except Exception as _e:
                logger.warning("Failed to save checkpoint to GCS: %s", _e)

            # Write continuation queue item to Firestore
            wrote_continuation = False
            try:
                from pipeline_client.backend.firestore_logger import _get_db

                db = _get_db()
                if not db:
                    raise RuntimeError("Firestore is not available for continuation handoff")
                continuation_options = dict(options)
                continuation_options["enabled_steps"] = remaining
                continuation_options["all_enabled_steps"] = all_enabled_steps
                continuation_options["completed_steps"] = list(dict.fromkeys(_completed_steps))
                continuation_options["is_continuation"] = True
                continuation_options["force_fresh"] = False
                continuation_options["logical_run_id"] = current_run_id
                continuation_options["run_id"] = current_run_id
                continuation_options.pop("deadline_at", None)
                from pipeline_client.agent.cost import _cost_ctx

                cost_snapshot = _cost_ctx.get()
                if isinstance(cost_snapshot, dict):
                    continuation_options["prior_agent_metrics"] = {
                        "prompt_tokens": cost_snapshot.get("prompt_tokens", 0),
                        "completion_tokens": cost_snapshot.get("completion_tokens", 0),
                        "provider_cost_usd": cost_snapshot.get("provider_cost_usd", 0.0),
                        "priced_calls": cost_snapshot.get("priced_calls", 0),
                        "unpriced_calls": cost_snapshot.get("unpriced_calls", 0),
                        "serper_calls": cost_snapshot.get("serper_calls", 0),
                        "searlo_calls": cost_snapshot.get("searlo_calls", 0),
                        "search_budget_blocked": cost_snapshot.get("search_budget_blocked", 0),
                        "token_budget_nudges": cost_snapshot.get("token_budget_nudges", 0),
                        "duration_s": float((options.get("prior_agent_metrics") or {}).get("duration_s", 0.0) or 0.0)
                        + (time.perf_counter() - t0),
                        "context_requests": cost_snapshot.get("context_requests", 0),
                        "max_estimated_context_tokens": cost_snapshot.get("max_estimated_context_tokens", 0),
                        "max_context_window_tokens": cost_snapshot.get("max_context_window_tokens", 0),
                        "context_deduplicated_results": cost_snapshot.get("context_deduplicated_results", 0),
                        "context_compacted_results": cost_snapshot.get("context_compacted_results", 0),
                        "context_truncated_results": cost_snapshot.get("context_truncated_results", 0),
                        "context_dropped_tool_turns": cost_snapshot.get("context_dropped_tool_turns", 0),
                        "retry_rate_limits": cost_snapshot.get("retry_rate_limits", 0),
                        "retry_provider_failures": cost_snapshot.get("retry_provider_failures", 0),
                        "retry_deadline_exits": cost_snapshot.get("retry_deadline_exits", 0),
                        "model_breakdown": cost_snapshot.get("model_breakdown", {}),
                        "phase_breakdown": cost_snapshot.get("phase_breakdown", {}),
                        "page_fetches": cost_snapshot.get("page_fetches", 0),
                        "fetched_chars": cost_snapshot.get("fetched_chars", 0),
                        "page_budget_blocked": cost_snapshot.get("page_budget_blocked", 0),
                    }
                db.collection("pipeline_queue").document(item_id).set(
                    {
                        "id": item_id,
                        "race_id": current_race_id,
                        "run_id": continuation_run_id,
                        "status": "pending",
                        "options": continuation_options,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "is_continuation": True,
                        "parent_queue_item_id": queue_item_id,
                        "existing_data_gcs_path": checkpoint_gcs_path,
                    }
                )
                wrote_continuation = True
                logger.info("Continuation queue item %s written for steps: %s", item_id, remaining)
            except Exception as _e:
                logger.warning("Failed to write continuation queue item: %s", _e)
            if not wrote_continuation:
                raise HandoffFailed("Failed to create continuation queue item")

            # Keep one logical run active across physical function invocations.
            if _fs_logger:
                _fs_logger.mark_handoff(item_id, duration_ms=int((time.perf_counter() - t0) * 1000))

            raise HandoffTriggered(item_id, remaining, continuation_run_id)

        # Mutable holder so _trigger_handoff can read the latest race_json
        # (which is only known after run_agent returns, but we need the ref
        # before we define on_log below)
        race_json_holder: List[Optional[Dict[str, Any]]] = [existing_data if isinstance(existing_data, dict) else None]

        # --- Bounded log collector for response/debug metadata ---
        retention = RetentionConfig.from_env()
        agent_logs: Deque[Dict[str, Any]] = deque(maxlen=retention.run_log_buffer_size)
        log_stats = {"dropped": 0, "truncated": 0}

        debug_mode = bool(options.get("debug_mode"))
        debug_progress_buckets: Dict[str, int] = {}

        def on_log(level: str, message: str) -> None:
            _maybe_handoff("during log callback", step=_current_step, pct=0)
            safe_message, truncated = sanitize_log_message_with_metadata(
                message,
                max_chars=retention.max_log_message_chars,
            )
            log_entry = {
                "level": level,
                "message": safe_message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if truncated:
                log_entry["truncated"] = True
                log_stats["truncated"] += 1
            if len(agent_logs) == agent_logs.maxlen:
                log_stats["dropped"] += 1
            agent_logs.append(log_entry)
            if run_id and _run_manager:
                try:
                    _run_manager.add_run_log(run_id, log_entry)
                except Exception as _e:
                    logger.debug("Failed to persist run log entry: %s", _e)
            # Also write to Firestore so frontend can use onSnapshot
            if _fs_logger:
                _fs_logger.log(
                    level,
                    message,
                    step=_current_step,
                    race_id=race_id,
                    extra={"event": "agent_log"} if debug_mode else None,
                )

        # Run the agent
        try:
            race_json = await run_agent(
                race_id,
                on_log=on_log,
                cheap_mode=cheap_mode,
                existing_data=existing_data,
                research_model=options.get("research_model"),
                claude_model=options.get("claude_model"),
                gemini_model=options.get("gemini_model"),
                grok_model=options.get("grok_model"),
                model_profile=options.get("model_profile"),
                model_overrides=options.get("model_overrides"),
                review_providers=options.get("review_providers"),
                enabled_steps=enabled_steps,
                step_tracker=step_tracker,
                max_candidates=options.get("max_candidates"),
                target_no_info=options.get("target_no_info", False),
                candidate_names=options.get("candidate_names"),
                goal=options.get("goal"),
                resume_partial=bool(options.get("is_continuation") or options.get("resume_partial")),
                continue_incomplete_work=True,
                reject_empty_candidates=True,
                prior_agent_metrics=options.get("prior_agent_metrics"),
                run_budget=run_budget,
            )
        except (RunBudgetExceeded, PipelineWorkRemaining) as exc:
            from pipeline_client.agent.cost import record_retry_metric

            if isinstance(exc, RunBudgetExceeded):
                record_retry_metric("deadline_exits")
                logger.warning("Run budget exhausted: %s", exc)
                reason = "before run budget exhaustion"
            else:
                logger.info("Durable pipeline work remains: %s", exc)
                reason = "for remaining durable work"
            _maybe_handoff(reason, step=_current_step, pct=0, force=True)
            raise

        # Update checkpoint holder so handoff (if somehow triggered post-agent) has latest data
        race_json_holder[0] = race_json

        # Save as draft (not published) — admin must explicitly publish
        draft_path = await self._save_draft(
            race_id,
            race_json,
            verified_baseline_candidate_names=verified_baseline_candidate_names,
        )

        # Update race record metadata from the new draft data
        if not queue_item_id:
            try:
                from pipeline_client.backend.race_manager import race_manager

                race_manager.update_race_metadata(race_id, race_json)
            except Exception:
                logger.warning("Failed to update race metadata after draft save", exc_info=True)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(f"Agent: saved draft {race_id} to {draft_path} in {duration_ms}ms")

        # Record pipeline metrics (fire-and-forget)
        try:
            from pipeline_client.backend.pipeline_metrics import get_pipeline_metrics_store

            agent_metrics = race_json.get("agent_metrics")
            rid = run_id or f"{race_id}-{int(t0)}"
            candidate_count = len(race_json.get("candidates") or [])
            _cheap_mode = bool(options.get("cheap_mode", True))
            serper_calls = 0
            if isinstance(agent_metrics, dict):
                serper_calls = agent_metrics.get("serper_calls", 0)
            await get_pipeline_metrics_store().record_run(
                rid,
                race_id,
                agent_metrics,
                "completed",
                candidate_count=candidate_count,
                cheap_mode=_cheap_mode,
                serper_calls=serper_calls,
            )
        except Exception:
            logger.warning("Failed to record pipeline metrics", exc_info=True)

        run_health = race_json.get("run_health") if isinstance(race_json, dict) else None
        if _fs_logger:
            _fs_logger.mark_completed(duration_ms=duration_ms, run_health=run_health)

        return {
            "race_id": race_id,
            "race_json": race_json,
            "draft_path": str(draft_path),
            "duration_ms": duration_ms,
            "agent_logs": list(agent_logs),
            "log_stats": log_stats,
            "status": "draft",
            "run_health": run_health,
        }

    async def _save_draft(
        self,
        race_id: str,
        race_json: Dict[str, Any],
        *,
        verified_baseline_candidate_names: Set[str] | None = None,
    ) -> Path:
        """Write RaceJSON to drafts/, retiring the previous active draft if present."""
        logger = logging.getLogger("pipeline")
        drafts_dir = local_paths.drafts_dir
        drafts_dir.mkdir(parents=True, exist_ok=True)

        output_path = drafts_dir / f"{race_id}.json"

        # Guard against saving a partial/corrupted LLM response
        candidates = race_json.get("candidates")
        if not isinstance(candidates, list) or len(candidates) == 0:
            raise ValueError(
                f"Refusing to save draft '{race_id}': 'candidates' is missing or empty. "
                f"Top-level keys present: {list(race_json.keys())}. "
                "This usually means the LLM returned a partial object. Re-queue the race."
            )
        candidate_names = [_candidate_name(candidate) for candidate in candidates]
        if all(_is_placeholder_candidate_name(name) for name in candidate_names):
            raise ValueError(
                f"Refusing to save draft '{race_id}': all candidate names are placeholders: {candidate_names}. "
                "Re-queue the race with candidate_names or inspect discovery output."
            )
        from pipeline_client.agent.handlers import _qualifying_candidate_addition_sources, _roster_source_rejection_summary

        baseline_names = {name.casefold() for name in (verified_baseline_candidate_names or set())}
        unsupported_additions: List[str] = []
        for candidate in candidates:
            name = _candidate_name(candidate)
            if not name or name.casefold() in baseline_names:
                continue
            # Newly added candidates keep the strict corroboration rule: this is the
            # anti-fabrication boundary. Candidates already in the baseline are exempt.
            raw_sources = candidate.get("roster_sources") if isinstance(candidate, dict) else None
            sources = _qualifying_candidate_addition_sources(
                raw_sources,
                candidate_name=name,
                race_id=race_id,
            )
            if not sources:
                detail = _roster_source_rejection_summary(raw_sources, candidate_name=name, race_id=race_id)
                unsupported_additions.append(f"{name} ({detail})")
            elif isinstance(candidate, dict):
                candidate["roster_sources"] = sources
        if unsupported_additions:
            raise ValueError(
                f"Refusing to save draft '{race_id}': new candidate(s) lack qualifying current-cycle "
                f"exact-contest evidence: {'; '.join(unsupported_additions)}."
            )

        json_str = json.dumps(race_json, indent=2, default=str)

        tmp_path = output_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            f.write(json_str)

        if output_path.exists():
            self._archive_local_version(output_path, race_id, source="draft")
        tmp_path.replace(output_path)

        # Also upload to GCS drafts/ prefix. Archive the previous active draft
        # before overwriting it, but do not delete it first; if upload fails, the
        # old active object remains available.
        await self._archive_gcs_version(race_id, src_prefix="drafts", source="draft")
        await self._upload_to_gcs(race_id, json_str, prefix="drafts")

        return output_path

    def _retired_blob_name(self, race_id: str, source: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"retired/{race_id}/{stamp}-{source}.json"

    def _archive_local_version(self, source_path: Path, race_id: str, *, source: str) -> Path:
        retired_dir = local_paths.retired_dir / race_id
        retired_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        retired_path = retired_dir / f"{stamp}-{source}.json"
        shutil.copy2(source_path, retired_path)
        return retired_path

    async def _archive_gcs_version(self, race_id: str, *, src_prefix: str, source: str) -> bool:
        """Copy an active GCS object into retired/ if it exists."""
        logger = logging.getLogger("pipeline")
        from pipeline_client.backend.settings import settings

        gcs_bucket = settings.gcs_bucket
        if not gcs_bucket:
            return False

        try:
            client = self._get_storage_client()
            if client is None:
                return False
            bucket = client.bucket(gcs_bucket)
            src_blob = bucket.blob(f"{src_prefix}/{race_id}.json")
            if not src_blob.exists():
                return False

            retired_blob = bucket.blob(self._retired_blob_name(race_id, source))
            bucket.copy_blob(src_blob, bucket, retired_blob.name)
            logger.info(
                "Archived %s from GCS %s/ to gs://%s/%s",
                race_id,
                src_prefix,
                gcs_bucket,
                retired_blob.name,
            )
            return True
        except Exception as e:
            logger.warning("Failed to archive %s from GCS %s/: %s", race_id, src_prefix, e)
        return False

    async def _upload_to_gcs(self, race_id: str, json_str: str, prefix: str = "drafts") -> None:
        """Upload race JSON to Google Cloud Storage under the given prefix.

        Runs in both cloud and local environments — if a bucket env var is set
        (e.g. via .env), the pipeline always pushes to GCS.
        """
        logger = logging.getLogger("pipeline")
        from pipeline_client.backend.settings import settings

        gcs_bucket = settings.gcs_bucket
        if not gcs_bucket:
            return

        try:
            client = self._get_storage_client()
            if client is None:
                return
            bucket = client.bucket(gcs_bucket)
            blob = bucket.blob(f"{prefix}/{race_id}.json")
            blob.upload_from_string(json_str, content_type="application/json")
            logger.info(f"Uploaded {race_id} to GCS: gs://{gcs_bucket}/{prefix}/{race_id}.json")
        except Exception as e:
            logger.warning(f"Failed to upload {race_id} to GCS {prefix}/: {e}")

    async def _load_existing_from_gcs(self, race_id: str, *, baseline_source: str = "latest") -> Dict[str, Any] | None:
        """Load existing race data from GCS so deployed containers use update mode.

        ``latest`` checks drafts/ first (most recent agent output), then falls
        back to races/ (published). ``published`` reads only races/, which lets
        targeted repair runs ignore an unrelated or defective draft. Returns
        *None* when GCS is not configured or the race doesn't exist.
        """
        logger = logging.getLogger("pipeline")
        from pipeline_client.backend.settings import settings

        gcs_bucket = settings.gcs_bucket
        if not gcs_bucket:
            return None

        try:
            client = self._get_storage_client()
            if client is None:
                return None
            bucket = client.bucket(gcs_bucket)

            prefixes = ("races",) if baseline_source == "published" else ("drafts", "races")
            for prefix in prefixes:
                blob = bucket.blob(f"{prefix}/{race_id}.json")
                if not blob.exists():
                    continue
                data = json.loads(blob.download_as_text())
                if not isinstance(data.get("candidates"), list) or len(data["candidates"]) == 0:
                    logger.warning(
                        f"Existing GCS file {prefix}/{race_id} has no candidates " f"(keys: {list(data.keys())}) — skipping"
                    )
                    continue
                logger.info(f"Loaded existing {race_id} from GCS {prefix}/ for update mode")
                return data

            return None
        except Exception as e:
            logger.warning(f"Failed to load existing {race_id} from GCS: {e}")
            return None
