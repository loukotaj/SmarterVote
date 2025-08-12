import asyncio
import time
import logging
from typing import Any, Dict
from .models import RunRequest, RunResponse, RunStatus
from .step_registry import get_handler
from .storage import new_artifact_id, save_artifact
from .settings import settings
from .logging_manager import logging_manager
from .run_manager import run_manager


def _merge_options(req_opts) -> Dict[str, Any]:
    base = {
        "skip_llm_apis": settings.skip_llm_apis,
        "skip_external_apis": settings.skip_external_apis,
        "skip_network_calls": settings.skip_network_calls,
        "skip_cloud_services": settings.skip_cloud_services,
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
                import asyncio

                asyncio.create_task(logging_manager.broadcast_message(message_data))

            main_loop.call_soon_threadsafe(schedule_broadcast)
    except Exception:
        # Fail silently
        pass


async def run_step_async(step: str, request: RunRequest) -> RunResponse:
    """Run a pipeline step with comprehensive logging and run tracking."""
    # Create run record
    run_info = run_manager.create_run(step, request)
    run_id = run_info.run_id

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

        # Mark run as started
        run_manager.start_run(run_id)
        await logging_manager.send_run_status(run_id, "running")

        context_logger.info(f"Getting handler for step '{step}'")
        handler = get_handler(step)

        context_logger.info(f"Executing step handler...")

        # Run the handler directly in the main event loop context
        # This allows logging to work properly with WebSocket broadcasting
        output = await handler.handle(request.payload, options)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        context_logger.info(f"Step completed successfully in {duration_ms}ms")

        artifact_id = None
        if options.get("save_artifact", True):
            context_logger.info("Saving artifact...")
            artifact_id = new_artifact_id(step)
            save_artifact(
                artifact_id,
                {
                    "step": step,
                    "input": request.payload,
                    "options": options,
                    "output": output,
                    "duration_ms": duration_ms,
                    "run_id": run_id,
                },
            )
            context_logger.info(f"Artifact saved with ID: {artifact_id}")

        # Mark run as completed
        run_manager.complete_run(run_id, artifact_id, duration_ms)
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
        error_msg = str(e)

        context_logger.error(f"Pipeline step '{step}' failed: {error_msg}", exc_info=True)

        # Mark run as failed
        run_manager.fail_run(run_id, error_msg, duration_ms)
        await logging_manager.send_run_status(run_id, "failed", error=error_msg, duration_ms=duration_ms)

        # Send run_failed message that frontend expects
        _safe_broadcast({"type": "run_failed", "run_id": run_id, "error": error_msg, "duration_ms": duration_ms})

        return RunResponse(step=step, ok=False, output=None, error=error_msg, duration_ms=duration_ms, meta={"run_id": run_id})


def run_step(step: str, request: RunRequest) -> RunResponse:
    return asyncio.run(run_step_async(step, request))
