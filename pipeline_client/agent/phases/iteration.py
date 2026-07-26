"""Review iteration — tools-mode pass addressing reviewer flags."""

import copy
import json
from typing import Any, Dict, List, Optional

from ..handlers import _make_editing_handlers
from ..prompts import CANONICAL_ISSUES, ITERATE_META_USER, ITERATE_SYSTEM, ITERATE_USER
from ..review_flags import format_review_flags as _format_review_flags
from ..run_budget import RunBudget, RunBudgetExceeded
from ..selection import _scale_iterations
from ..tools import BACKGROUND_TOOLS, CANDIDATE_TOOLS, ISSUE_TOOLS, RACE_TOOLS, READ_PROFILE_TOOL, RECORD_TOOLS, ROSTER_TOOLS
from ..utils import make_logger
from ._common import (
    _await_with_run_budget,
    _candidate_name,
    _mark_pipeline_unit_complete,
    _pipeline_completed_units,
    _race_identity_context,
)


async def _run_iteration_pass(
    race_id: str,
    race_json: Dict[str, Any],
    reviews: List[Dict[str, Any]],
    *,
    model: str,
    on_log: Any | None = None,
    on_progress: Any | None = None,
    max_iterations: int = 20,
    resume_partial: bool = False,
    unit_prefix: str = "iteration:1",
    run_budget: RunBudget | None = None,
) -> Optional[Dict[str, Any]]:
    """Run a single iteration pass addressing review flags (tools mode)."""
    from . import _agent_loop, _candidate_source_hints

    log = make_logger(on_log)

    candidates = race_json.get("candidates", [])
    n = len(candidates)
    iterate_iters = _scale_iterations(max_iterations, n, per_candidate=5, minimum=15)
    iters_per_cand = max(10, iterate_iters // max(n, 1))

    log("info", f"  Iteration: addressing review flags for {n} candidates (tools mode)")

    working = copy.deepcopy(race_json)
    identity_context = _race_identity_context(working)
    completed_units = _pipeline_completed_units(working)
    if not resume_partial:
        completed_units = {unit for unit in completed_units if not unit.startswith(f"{unit_prefix}:")}
        working["pipeline_state"]["completed_units"] = sorted(completed_units)

    candidate_units = [
        (index, candidate, f"{unit_prefix}:{_candidate_name(candidate)}")
        for index, candidate in enumerate(working.get("candidates", []))
        if isinstance(candidate, dict) and _candidate_name(candidate)
    ]
    expected_units = {unit for _, _, unit in candidate_units}

    def checkpoint_progress(label: str) -> None:
        if on_progress is None:
            return
        completed = len(expected_units & _pipeline_completed_units(working))
        pct = int(completed / max(len(expected_units), 1) * 100)
        on_progress(pct, label, working)

    all_tools = (
        ROSTER_TOOLS + CANDIDATE_TOOLS + ISSUE_TOOLS + RECORD_TOOLS + BACKGROUND_TOOLS + RACE_TOOLS + [READ_PROFILE_TOOL]
    )
    any_success = False

    for candidate_index, candidate, unit_id in candidate_units:
        if unit_id in completed_units:
            log("info", f"  Iteration checkpoint already complete for {_candidate_name(candidate)}; skipping")
            continue
        cname = _candidate_name(candidate)
        # Scoped to this candidate only: a mistaken candidate_name in a tool call during
        # this turn is rejected instead of silently corrupting a different candidate's data.
        handlers = _make_editing_handlers(working, log, restrict_to_candidate=cname)
        candidate_website, candidate_issue_urls = await _await_with_run_budget(
            _candidate_source_hints(working, cname),
            run_budget=run_budget,
            requested_timeout=20.0,
            operation="candidate source hint crawl",
        )
        issue_hint_text = ", ".join(candidate_issue_urls) if candidate_issue_urls else "(none found)"
        log("info", f"  Iterating on {cname}...")
        try:
            await _agent_loop(
                ITERATE_SYSTEM,
                ITERATE_USER.format(
                    race_id=race_id,
                    candidate_name=cname,
                    candidate_website=candidate_website,
                    candidate_issue_urls=issue_hint_text,
                    candidate_json=json.dumps(candidate, indent=2, default=str),
                    race_identity_context=identity_context,
                    review_flags=_format_review_flags(
                        reviews,
                        candidate_index=candidate_index,
                        candidate_name=cname,
                        include_global=False,
                    ),
                    all_issues=", ".join(CANONICAL_ISSUES),
                ),
                model=model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=iters_per_cand,
                phase_name=f"iterate-{cname[:20]}",
                max_tokens=8192,
                extra_tools=all_tools,
                extra_tool_handlers=handlers,
                tools_mode=True,
                run_budget=run_budget,
            )
            any_success = True
        except RunBudgetExceeded:
            raise
        except Exception as exc:
            log("warning", f"  Iteration failed for {cname}: {exc} — keeping existing")

        _mark_pipeline_unit_complete(working, unit_id)
        completed_units.add(unit_id)
        checkpoint_progress(f"Review iteration checkpoint: {cname}")

    log("info", "  Iterating on race metadata...")
    try:
        # Race-wide pass (not scoped to any single candidate) — RACE_TOOLS has no
        # candidate_name-taking tools, so an unrestricted handler set is correct here.
        meta_handlers = _make_editing_handlers(working, log)
        await _agent_loop(
            ITERATE_SYSTEM,
            ITERATE_META_USER.format(
                race_id=race_id,
                race_description=working.get("description", ""),
                race_identity_context=identity_context,
                polling_json=json.dumps(working.get("polling", []), indent=2, default=str),
                review_flags=_format_review_flags(reviews, include_global=True),
            ),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max(5, iters_per_cand // 2),
            phase_name="iterate-meta",
            max_tokens=4096,
            extra_tools=RACE_TOOLS + [READ_PROFILE_TOOL],
            extra_tool_handlers=meta_handlers,
            tools_mode=True,
            run_budget=run_budget,
        )
        any_success = True
    except RunBudgetExceeded:
        raise
    except Exception as exc:
        log("warning", f"  Iteration meta failed: {exc} — keeping existing meta")

    if not any_success and not expected_units.issubset(_pipeline_completed_units(working)):
        log("warning", "  All iteration calls failed — keeping original")
        return None

    working.setdefault("id", race_id)
    return working
