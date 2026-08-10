"""Phase 3: refinement — tools-mode per-candidate and race-meta cleanup."""

import json
import time

from ..handlers import _make_editing_handlers
from ..prompts import CANONICAL_ISSUES, REFINE_META_USER, REFINE_SYSTEM, REFINE_USER
from ..run_budget import RunBudgetExceeded
from ..tools import BACKGROUND_TOOLS, CANDIDATE_TOOLS, DESCRIPTION_TOOLS, ISSUE_TOOLS, READ_PROFILE_TOOL, RECORD_TOOLS
from ._common import (
    _await_with_run_budget,
    _classify_exception,
    _mark_pipeline_unit_complete,
    _pipeline_completed_units,
    _record_step_failure,
)
from .context import PhaseContext


async def run_refinement_phase(ctx: PhaseContext) -> None:
    """Refine each selected candidate one at a time, then refine race metadata."""
    race_json = ctx.race_json
    race_id = ctx.race_id
    selected_name_set = ctx.selected_name_set
    model = ctx.model
    on_log = ctx.on_log
    step_enabled = ctx.step_enabled
    track = ctx.track
    is_update = ctx.is_update
    refine_iters = ctx.refine_iters
    log = ctx.log
    prefix = ctx.prefix
    resume_partial = ctx.resume_partial
    run_budget = ctx.run_budget
    from . import _agent_loop, _candidate_source_hints

    if not step_enabled("refinement"):
        log("info", f"{prefix} 3: Refinement — SKIPPED")
        track("skip", "refinement")
        return

    track("start", "refinement")
    ref_t0 = time.perf_counter()
    handlers = _make_editing_handlers(race_json, log)
    cand_list = [c for c in race_json.get("candidates", []) if isinstance(c, dict) and c.get("name") in selected_name_set]
    cand_names_in_json = [c["name"] for c in cand_list]
    n_cands = len(cand_list)
    refinement_units = _pipeline_completed_units(race_json)
    log("info", f"{prefix} 3: Refining profile (one candidate at a time, tools mode)...")
    for ci, candidate in enumerate(cand_list):
        cname = candidate["name"]
        unit_id = f"refinement:{cname}"
        if resume_partial and unit_id in refinement_units:
            track(
                "progress",
                "refinement",
                pct=int(((ci + 1) / max(n_cands, 1)) * 100),
                message=f"Refinement checkpoint: {cname} ({ci + 1}/{n_cands})",
                race_json=race_json,
            )
            continue
        candidate_website, candidate_issue_urls = await _await_with_run_budget(
            _candidate_source_hints(race_json, cname),
            run_budget=run_budget,
            requested_timeout=20.0,
            operation="candidate source hint crawl",
        )
        issue_hint_text = ", ".join(candidate_issue_urls) if candidate_issue_urls else "(none found)"
        log("info", f"  Refining {cname}...")
        track(
            "progress",
            "refinement",
            pct=int((ci / max(n_cands, 1)) * 100),
            message=f"Refinement: {cname} ({ci + 1}/{n_cands})",
            race_json=race_json,
        )
        try:
            refine_prefix = "upd-refine" if is_update else "refine"
            await _agent_loop(
                REFINE_SYSTEM,
                REFINE_USER.format(
                    race_id=race_id,
                    candidate_name=cname,
                    candidate_website=candidate_website,
                    candidate_issue_urls=issue_hint_text,
                    candidate_json=json.dumps(candidate, indent=2, default=str),
                    race_description=race_json.get("description", ""),
                    other_candidates=", ".join(cn for cn in cand_names_in_json if cn != cname),
                    all_issues=", ".join(CANONICAL_ISSUES),
                ),
                model=model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=max(8, refine_iters // max(n_cands, 1)),
                phase_name=f"{refine_prefix}-{cname[:20]}",
                max_tokens=8192,
                extra_tools=CANDIDATE_TOOLS + ISSUE_TOOLS + RECORD_TOOLS + BACKGROUND_TOOLS + [READ_PROFILE_TOOL],
                extra_tool_handlers=handlers,
                tools_mode=True,
                run_budget=run_budget,
            )
        except RunBudgetExceeded:
            raise
        except Exception as exc:
            log("warning", f"  Refine failed for {cname}: {exc} — keeping existing")
            _record_step_failure(race_json, "refinement", _classify_exception(exc), f"{cname}: {exc}")
        _mark_pipeline_unit_complete(race_json, unit_id)
        refinement_units.add(unit_id)
        track(
            "progress",
            "refinement",
            pct=int(((ci + 1) / max(n_cands, 1)) * 100),
            message=f"Refinement checkpoint: {cname} ({ci + 1}/{n_cands})",
            race_json=race_json,
        )

    # Meta refinement (description only) — tools mode
    meta_unit_id = "refinement:meta"
    if not (resume_partial and meta_unit_id in refinement_units):
        log("info", "  Refining race metadata...")
        try:
            await _agent_loop(
                REFINE_SYSTEM,
                REFINE_META_USER.format(
                    race_id=race_id,
                    race_description=race_json.get("description", ""),
                ),
                model=model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=max(6, refine_iters // 3),
                phase_name=f"{'upd-' if is_update else ''}refine-meta",
                max_tokens=4096,
                extra_tools=DESCRIPTION_TOOLS + [READ_PROFILE_TOOL],
                extra_tool_handlers=handlers,
                tools_mode=True,
                run_budget=run_budget,
            )
        except RunBudgetExceeded:
            raise
        except Exception as exc:
            log("warning", f"  Refine meta failed: {exc} — keeping existing meta")
            _record_step_failure(race_json, "refinement", _classify_exception(exc), f"meta: {exc}")
        _mark_pipeline_unit_complete(race_json, meta_unit_id)
        refinement_units.add(meta_unit_id)
        track(
            "progress",
            "refinement",
            pct=100,
            message="Refinement checkpoint: race metadata",
            race_json=race_json,
        )
    track("complete", "refinement", duration_ms=int((time.perf_counter() - ref_t0) * 1000), race_json=race_json)
