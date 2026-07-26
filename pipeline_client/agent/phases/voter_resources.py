"""Phase 5: verify and compile local voter resources."""

import time
from typing import Any, Dict

from ..handlers import _make_editing_handlers
from ..prompts import VOTER_RESOURCES_SYSTEM, VOTER_RESOURCES_USER
from ..run_budget import RunBudget, RunBudgetExceeded
from ..tools import READ_PROFILE_TOOL, VOTER_RESOURCE_TOOLS
from ._common import _classify_exception, _record_step_failure


async def run_voter_resources_phase(
    race_json: Dict[str, Any],
    race_id: str,
    *,
    small_model: str,
    on_log: Any,
    max_iterations: int,
    step_enabled: Any,
    track: Any,
    is_update: bool,
    log: Any,
    prefix: str,
    run_budget: RunBudget | None,
) -> None:
    """Verify local registration and voting info for the race's jurisdiction."""
    from . import _agent_loop

    if not step_enabled("voter_resources"):
        track("skip", "voter_resources")
        return

    track("start", "voter_resources")
    resources_t0 = time.perf_counter()
    handlers = _make_editing_handlers(race_json, log)
    log("info", f"{prefix} 5: Verifying voter resources...")
    try:
        await _agent_loop(
            VOTER_RESOURCES_SYSTEM,
            VOTER_RESOURCES_USER.format(
                race_id=race_id,
                office=race_json.get("office") or "",
                jurisdiction=race_json.get("jurisdiction") or "",
                state=race_json.get("state") or "",
            ),
            model=small_model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=min(max_iterations, 8),
            phase_name=f"{'update-' if is_update else ''}voter-resources",
            max_tokens=4096,
            extra_tools=VOTER_RESOURCE_TOOLS + [READ_PROFILE_TOOL],
            extra_tool_handlers=handlers,
            tools_mode=True,
            run_budget=run_budget,
        )
    except RunBudgetExceeded:
        raise
    except Exception as exc:
        log("warning", f"  Voter resources phase failed: {exc}")
        _record_step_failure(race_json, "voter_resources", _classify_exception(exc), str(exc))
    track(
        "complete",
        "voter_resources",
        duration_ms=int((time.perf_counter() - resources_t0) * 1000),
        race_json=race_json,
    )
