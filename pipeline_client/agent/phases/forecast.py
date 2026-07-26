"""Phase 4b: generate a chamber/race outcome forecast."""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict

from ..handlers import _make_editing_handlers
from ..prompts import FORECAST_SYSTEM, FORECAST_USER
from ..run_budget import RunBudget, RunBudgetExceeded
from ..tools import FORECAST_TOOLS, READ_PROFILE_TOOL
from ._common import _await_with_run_budget, _classify_exception, _race_identity_context, _record_step_failure


async def run_forecast_phase(
    race_json: Dict[str, Any],
    race_id: str,
    *,
    model: str,
    on_log: Any,
    max_iterations: int,
    step_enabled: Any,
    track: Any,
    is_update: bool,
    log: Any,
    prefix: str,
    run_budget: RunBudget | None,
) -> None:
    """Generate a race forecast, incorporating Kalshi market signals when available."""
    from . import _agent_loop, fetch_kalshi_market_signals

    if not step_enabled("forecast"):
        track("skip", "forecast")
        return

    track("start", "forecast")
    forecast_t0 = time.perf_counter()
    handlers = _make_editing_handlers(race_json, log)
    log("info", f"{prefix} 4b: Generating race forecast...")
    try:
        compact_candidates = [
            {
                "name": candidate.get("name"),
                "party": candidate.get("party"),
                "incumbent": candidate.get("incumbent", False),
                "withdrawn": candidate.get("withdrawn", False),
                "summary": candidate.get("summary", ""),
                "donor_summary": candidate.get("donor_summary"),
                "voting_summary": candidate.get("voting_summary"),
            }
            for candidate in race_json.get("candidates", [])
            if isinstance(candidate, dict)
        ]
        market_signals: list[dict[str, Any]] = []
        try:
            market_signals = await _await_with_run_budget(
                fetch_kalshi_market_signals(race_id),
                run_budget=run_budget,
                requested_timeout=10.0,
                operation="Kalshi market data fetch",
            )
            if market_signals:
                log("info", f"  Forecast: loaded {len(market_signals)} Kalshi market signal(s)")
        except RunBudgetExceeded:
            raise
        except Exception as exc:
            log("warning", f"  Forecast: Kalshi market signals unavailable: {exc}")

        await _agent_loop(
            FORECAST_SYSTEM,
            FORECAST_USER.format(
                race_id=race_id,
                current_date=datetime.now(timezone.utc).date().isoformat(),
                office=race_json.get("office") or "",
                jurisdiction=race_json.get("jurisdiction") or "",
                state=race_json.get("state") or "",
                district=race_json.get("district") or "",
                description=race_json.get("description") or "",
                race_identity_context=_race_identity_context(race_json),
                candidates_json=json.dumps(compact_candidates, indent=2, default=str),
                polling_note=race_json.get("polling_note") or "",
                polling_json=json.dumps(race_json.get("polling", []), indent=2, default=str),
                market_signals_json=json.dumps(market_signals, indent=2, default=str),
                forecast_json=json.dumps(race_json.get("forecast"), indent=2, default=str),
            ),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=min(max_iterations, 4),
            phase_name=f"{'update-' if is_update else ''}forecast",
            max_tokens=4096,
            extra_tools=FORECAST_TOOLS + [READ_PROFILE_TOOL],
            extra_tool_handlers=handlers,
            tools_mode=True,
            run_budget=run_budget,
            allow_search_tools=False,
        )
        if isinstance(race_json.get("forecast"), dict):
            race_json["forecast"]["model"] = model
            race_json["forecast"]["market_signals"] = market_signals
    except RunBudgetExceeded:
        raise
    except Exception as exc:
        log("warning", f"  Forecast phase failed: {exc}")
        _record_step_failure(race_json, "forecast", _classify_exception(exc), str(exc))
    track("complete", "forecast", duration_ms=int((time.perf_counter() - forecast_t0) * 1000), race_json=race_json)
