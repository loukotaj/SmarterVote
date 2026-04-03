import asyncio
import json
import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .logging_manager import logging_manager
from .models import RunRequest, RunResponse, RunStatus
from .race_manager import race_manager
from .run_manager import run_manager
from .step_registry import get_handler
from .storage import new_artifact_id, save_artifact


async def _run_and_save_post_analysis(run_id: str, race_id: str, logs: list) -> None:
    """Run Gemini Flash post-run analysis and broadcast the result as log lines."""
    _log = logging.getLogger("pipeline")
    try:
        from pipeline_client.agent.review import run_post_run_analysis

        result = await run_post_run_analysis(run_id, race_id, logs)
        if result.get("skipped"):
            _log.info(f"Post-run analysis skipped: {result.get('reason')}")
            return

        analysis_text: str = result.get("analysis", "").strip()
        model = result.get("model", "?")
        _log.info(f"━━━ Post-run analysis ({model}) ━━━")
        for line in analysis_text.splitlines():
            _log.info(line)
        _log.info("━━━ End post-run analysis ━━━")

        # Also push the full block as a single broadcast so the live log panel shows it
        _safe_broadcast({
            "type": "log",
            "level": "info",
            "message": f"[post-run analysis]\n{analysis_text}",
            "run_id": run_id,
        })
    except Exception:
        _log.warning("Post-run analysis failed", exc_info=True)


def _merge_options(req_opts) -> Dict[str, Any]:
    """Merge RunOptions from the RunRequest with defaults.

    Returns a flat dict of option key/value pairs used by the pipeline runner
    and passed through to the step handler.
    """
    base = {
        "save_artifact": True,
    }
    if req_opts is None:
        return base
    for k, v in req_opts.model_dump(exclude_unset=True).items():
        base[k] = v
    return base


def _safe_broadcast(message_data):
    """Safely broadcast a message using the logging manager."""
    try:
        # Try to get the main event loop and schedule the broadcast
        main_loop = getattr(logging_manager, "_main_loop", None)
        if main_loop and not main_loop.is_closed():

            def schedule_broadcast():
                asyncio.create_task(logging_manager.broadcast_message(message_data))

            main_loop.call_soon_threadsafe(schedule_broadcast)
    except Exception:
        # Fail silently
        pass


async def run_step_async(step: str, request: RunRequest, run_id: Optional[str] = None) -> RunResponse:
    """Run a pipeline step with comprehensive logging and run tracking."""
    if run_id:
        # Step was already added by create_run in the caller; just start the run
        # (which attaches the log handler so logs are captured in run_info.logs)
        if not run_manager.get_run(run_id):
            raise ValueError("Run not found")
        run_manager.start_run(run_id)
    else:
        run_info = run_manager.create_run([step], request)
        run_id = run_info.run_id
        run_manager.start_run(run_id)

    # Setup logging context
    logger = logging_manager.setup_logger("pipeline")

    # Extract race_id for logging context
    race_id = request.payload.get("race_id")

    # Add run context to logger
    class ContextAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            # Add context to each log record
            if "extra" not in kwargs:
                kwargs["extra"] = {}
            kwargs["extra"].update({"run_id": run_id, "step": step, "race_id": race_id})
            return msg, kwargs

    context_logger = ContextAdapter(logger, {})

    try:
        context_logger.info(f"Starting pipeline step '{step}' for race_id='{race_id}'")
        await logging_manager.send_run_status(run_id, "starting", step=step, race_id=race_id)

        # Send run_started message that frontend expects
        _safe_broadcast({"type": "run_started", "run_id": run_id, "step": step, "race_id": race_id})

        t0 = time.perf_counter()
        options = _merge_options(request.options)

        context_logger.info(f"Merged options: {options}")

        # Mark step as running
        run_manager.update_step_status(run_id, step, RunStatus.RUNNING)
        await logging_manager.send_run_status(run_id, "running")

        context_logger.info(f"Getting handler for step '{step}'")
        handler = get_handler(step)

        context_logger.info(f"Executing step handler...")

        # Pass run_id through options so the handler can track its own run
        options["run_id"] = run_id

        # Run the handler directly in the main event loop context
        # This allows logging to work properly with WebSocket broadcasting
        output = await handler.handle(request.payload, options)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        context_logger.info(f"Step completed successfully in {duration_ms}ms")

        artifact_id = None
        if options.get("save_artifact", True):
            try:
                context_logger.info("Saving artifact...")
                artifact_id = new_artifact_id(step)
                import json as _json
                save_artifact(
                    artifact_id,
                    {
                        "step": step,
                        "input": request.payload,
                        "options": options,
                        "output": _json.loads(_json.dumps(output, default=str)),
                        "duration_ms": duration_ms,
                        "run_id": run_id,
                    },
                )
                context_logger.info(f"Artifact saved with ID: {artifact_id}")
            except Exception:
                context_logger.warning("Artifact save failed; run will still complete", exc_info=True)
                artifact_id = None

        # Mark step as completed
        run_manager.update_step_status(run_id, step, RunStatus.COMPLETED, artifact_id, duration_ms)

        # Collect logs before complete_run removes the run from active memory
        run_logs = list(run_manager.get_run_logs(run_id) or [])

        # Mark the overall run as completed (persists to Firestore, detaches log handler)
        run_manager.complete_run(run_id, artifact_id, duration_ms)

        # Update race record: mark completed, save run to subcollection
        if race_id:
            try:
                race_manager.complete_run(race_id, run_id, artifact_id)
                # Save final run state to subcollection
                final_run = run_manager.get_run(run_id)
                if final_run:
                    race_manager.save_run(race_id, final_run)
            except Exception:
                context_logger.warning("Failed to update race record after completion", exc_info=True)

        # Fire post-run Gemini Flash improvement analysis (non-blocking)
        race_id_for_analysis = request.payload.get("race_id", "unknown")
        asyncio.create_task(
            _run_and_save_post_analysis(run_id, race_id_for_analysis, run_logs)
        )

        await logging_manager.send_run_status(run_id, "completed", artifact_id=artifact_id, duration_ms=duration_ms)

        # Send run_completed message that frontend expects
        _safe_broadcast(
            {
                "type": "run_completed",
                "run_id": run_id,
                "result": output,
                "artifact_id": artifact_id,
                "duration_ms": duration_ms,
            }
        )

        context_logger.info(f"Pipeline step '{step}' completed successfully")
        return RunResponse(
            step=step,
            ok=True,
            output=output,
            artifact_id=artifact_id,
            duration_ms=duration_ms,
            meta={"options": options, "run_id": run_id},
        )

    except Exception as e:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        error_msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        tb = traceback.format_exc()

        context_logger.error(f"Pipeline step '{step}' failed: {error_msg}\n{tb}")

        # Mark step and run as failed
        run_manager.update_step_status(run_id, step, RunStatus.FAILED, error=error_msg, duration_ms=duration_ms)
        run_manager.fail_run(run_id, error_msg, duration_ms)

        # Update race record: mark failed, save run to subcollection
        if race_id:
            try:
                race_manager.fail_run(race_id, run_id, error_msg)
                final_run = run_manager.get_run(run_id)
                if final_run:
                    race_manager.save_run(race_id, final_run)
            except Exception:
                context_logger.warning("Failed to update race record after failure", exc_info=True)

        await logging_manager.send_run_status(run_id, "failed", error=error_msg, duration_ms=duration_ms)

        # Send run_failed message that frontend expects
        _safe_broadcast({"type": "run_failed", "run_id": run_id, "error": error_msg, "duration_ms": duration_ms})

        return RunResponse(step=step, ok=False, output=None, error=error_msg, duration_ms=duration_ms, meta={"run_id": run_id})


def run_step(step: str, request: RunRequest, run_id: Optional[str] = None) -> RunResponse:
    return asyncio.run(run_step_async(step, request, run_id))
