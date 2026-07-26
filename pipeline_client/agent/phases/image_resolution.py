"""Phase 1b: verify and resolve direct candidate image URLs."""

import time
from typing import Any, Dict, Set

from ..images import resolve_candidate_images
from ..run_budget import RunBudget


async def run_image_resolution_phase(
    race_json: Dict[str, Any],
    race_id: str,
    *,
    selected_name_set: Set[str],
    small_model: str,
    on_log: Any,
    max_iterations: int,
    step_enabled: Any,
    track: Any,
    log: Any,
    prefix: str,
    run_budget: RunBudget | None,
) -> None:
    """Verify/resolve image URLs for the selected candidates (parallel)."""
    from . import _agent_loop

    if not step_enabled("images"):
        log("info", f"{prefix} 1b: Image resolution — SKIPPED")
        track("skip", "images")
        return

    track("start", "images")
    img_t0 = time.perf_counter()
    log("info", f"{prefix} 1b: Verifying and resolving candidate image URLs...")

    def _on_image_progress(pct: int, cand_name: str) -> None:
        track("progress", "images", pct=pct, message=f"Image Resolution: {cand_name}")

    await resolve_candidate_images(
        {
            "candidates": [
                c for c in race_json.get("candidates", []) if isinstance(c, dict) and c.get("name") in selected_name_set
            ],
            "office": race_json.get("office", ""),
            "jurisdiction": race_json.get("jurisdiction", ""),
        },
        agent_loop_fn=_agent_loop,
        model=small_model,
        on_log=on_log,
        race_id=race_id,
        max_iterations=min(max_iterations, 10),
        on_progress=_on_image_progress,
        run_budget=run_budget,
    )
    track("complete", "images", duration_ms=int((time.perf_counter() - img_t0) * 1000), race_json=race_json)
