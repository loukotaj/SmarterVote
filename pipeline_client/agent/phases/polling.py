"""Phase 4: refresh public polling data."""

import json
import time
from datetime import datetime, timezone

from ..handlers import _make_editing_handlers
from ..prompts import POLLING_SYSTEM, POLLING_USER
from ..run_budget import RunBudgetExceeded
from ..tools import POLLING_TOOLS, READ_PROFILE_TOOL
from ._common import _classify_exception, _race_identity_context, _record_step_failure
from .context import PhaseContext


async def run_polling_phase(ctx: PhaseContext) -> None:
    """Refresh available polling data for the race."""
    race_json = ctx.race_json
    race_id = ctx.race_id
    candidate_names = ctx.candidate_names
    small_model = ctx.small_model
    on_log = ctx.on_log
    max_iterations = ctx.max_iterations
    step_enabled = ctx.step_enabled
    track = ctx.track
    is_update = ctx.is_update
    log = ctx.log
    prefix = ctx.prefix
    run_budget = ctx.run_budget
    from . import _agent_loop

    if not step_enabled("polling"):
        track("skip", "polling")
        return

    track("start", "polling")
    polling_t0 = time.perf_counter()
    handlers = _make_editing_handlers(race_json, log)
    log("info", f"{prefix} 4: Refreshing public polling...")
    try:
        await _agent_loop(
            POLLING_SYSTEM,
            POLLING_USER.format(
                race_id=race_id,
                current_date=datetime.now(timezone.utc).date().isoformat(),
                candidate_names=", ".join(candidate_names),
                polling_json=json.dumps(race_json.get("polling", []), indent=2, default=str),
                race_identity_context=_race_identity_context(race_json),
            ),
            model=small_model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=min(max_iterations, 10),
            phase_name=f"{'update-' if is_update else ''}polling",
            max_tokens=8192,
            extra_tools=POLLING_TOOLS + [READ_PROFILE_TOOL],
            extra_tool_handlers=handlers,
            tools_mode=True,
            run_budget=run_budget,
        )
    except RunBudgetExceeded:
        raise
    except Exception as exc:
        log("warning", f"  Polling phase failed: {exc}")
        _record_step_failure(race_json, "polling", _classify_exception(exc), str(exc))
    track("complete", "polling", duration_ms=int((time.perf_counter() - polling_t0) * 1000), race_json=race_json)
