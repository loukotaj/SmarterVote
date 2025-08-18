"""Utilities for chaining pipeline steps using saved artifacts.

This module helps the pipeline client take the output of a previous run
and pass it through subsequent steps. It exposes helpers for building
payloads for each step and updating the JSON state after execution so the
next step receives the expected structure.
"""

from typing import Any, Dict, List, Optional, Tuple

from .models import RunRequest

# Ordered list of pipeline steps
PIPELINE_ORDER = [
    "step01a_metadata",
    "step01b_discovery",
    "step01c_fetch",
    "step01d_extract",
    "step01_ingest",
]


def state_from_artifact(artifact: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Create initial state JSON from a stored artifact."""

    step = artifact.get("step")
    state = dict(artifact.get("input", {}))
    output = artifact.get("output")
    state = update_state(step, state, output)
    return step, state


def build_payload(step: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """Construct the payload required for a given step."""

    if step == "step01a_metadata":
        return {"race_id": state["race_id"]}
    if step == "step01b_discovery":
        return {"race_id": state["race_id"], "race_json": state["race_json"]}
    if step == "step01c_fetch":
        return {"sources": state["sources"]}
    if step == "step01d_extract":
        return {"raw_content": state["raw_content"]}
    if step == "step01_ingest":
        return {"race_id": state["race_id"], "race_json": state["race_json"]}
    raise KeyError(f"Unknown step '{step}'")


def update_state(step: str, state: Dict[str, Any], output: Any) -> Dict[str, Any]:
    """Update the JSON state with the result of a step."""

    new_state = dict(state)
    if step == "step01a_metadata":
        if isinstance(output, dict) and "race_json" in output:
            new_state["race_json"] = output["race_json"]
            if "race_json_uri" in output:
                new_state["race_json_uri"] = output["race_json_uri"]
        else:
            new_state["race_json"] = output
    elif step == "step01b_discovery":
        new_state["sources"] = output
    elif step == "step01c_fetch":
        new_state["raw_content"] = output
    elif step == "step01d_extract":
        new_state["processed_content"] = output
    elif step == "step01_ingest":
        new_state["ingest_result"] = output
    return new_state


def remaining_steps(current_step: str, steps: Optional[List[str]]) -> List[str]:
    """Determine which steps to run after the current step."""

    try:
        idx = PIPELINE_ORDER.index(current_step)
    except ValueError as exc:  # pragma: no cover - defensive
        raise KeyError(f"Unknown step '{current_step}'") from exc

    remaining = PIPELINE_ORDER[idx + 1 :]

    if not steps:
        return remaining[:1]  # next step only
    if len(steps) == 1 and steps[0].lower() == "all":
        return remaining
    return [s for s in steps if s in remaining]


async def continue_run(
    run_id: str, steps: Optional[List[str]] = None, state: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Continue a pipeline run from a stored artifact.

    Parameters
    ----------
    run_id:
        The ID of the previously completed run whose artifact will seed the state.
    steps:
        Optional list of steps to execute. ``None`` or an empty list runs only the
        next step. ``["all"]`` runs all remaining steps.
    state:
        Optional JSON state allowing callers to edit data before execution.

    Returns
    -------
    dict
        A dictionary containing the updated state and metadata about the runs
        that were executed.
    """

    from datetime import datetime

    from .pipeline_runner import run_step_async
    from .run_manager import run_manager
    from .storage import load_artifact

    run_info = run_manager.get_run(run_id)
    if not run_info or not run_info.artifact_id:
        raise ValueError("Run not found or missing artifact")

    artifact = load_artifact(run_info.artifact_id)
    current_step, current_state = state_from_artifact(artifact)

    if state:
        current_state.update(state)

    steps_to_run = remaining_steps(current_step, steps)
    executed: List[Dict[str, Any]] = []

    for step in steps_to_run:
        payload = build_payload(step, current_state)
        response = await run_step_async(step, RunRequest(payload=payload), run_id=run_id)
        executed.append(
            {
                "step": step,
                "run_id": response.meta.get("run_id"),
                "artifact_id": response.artifact_id,
            }
        )
        if not response.ok:
            break
        current_state = update_state(step, current_state, response.output)
        current_step = step

    # If we've reached the end of the pipeline, mark the run complete
    if not remaining_steps(current_step, None):
        run_info = run_manager.get_run(run_id)
        if run_info:
            duration_ms = int((datetime.now() - run_info.started_at).total_seconds() * 1000)
            last_artifact = executed[-1]["artifact_id"] if executed else run_info.artifact_id
            run_manager.complete_run(run_id, last_artifact, duration_ms)

    updated_run = run_manager.get_run(run_id)
    steps_info = []
    if updated_run:
        steps_info = [s.model_dump(mode="json") for s in updated_run.steps]

    return {"state": current_state, "runs": executed, "last_step": current_step, "steps": steps_info}


__all__ = [
    "PIPELINE_ORDER",
    "state_from_artifact",
    "build_payload",
    "update_state",
    "remaining_steps",
    "continue_run",
]
