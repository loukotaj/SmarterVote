"""The per-run state every phase needs, bundled once instead of threaded.

``_run_shared_phases`` passed the same fifteen arguments to each of seven
phases, and every phase repeated them in its own signature. Adding one
phase-level concern meant editing eight files and touching nothing that had
anything to do with the concern.

All of these values are computed once when a run starts and do not change while
it executes, so they belong together. Phase-specific behaviour still lives in
each phase; this only carries what they all read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ..run_budget import RunBudget


@dataclass(frozen=True)
class PhaseContext:
    """Immutable run state shared by every phase.

    The dataclass is frozen, but ``race_json`` is a mutable dict on purpose:
    phases mutate the race document in place, which is the pipeline's existing
    contract. Freezing the container stops a phase from swapping in a *different*
    document or quietly rewriting run settings mid-run — the failure that is hard
    to trace — while leaving the intended mutation path alone.
    """

    race_json: Dict[str, Any]
    race_id: str

    model: str
    small_model: str

    on_log: Any
    log: Any
    max_iterations: int
    step_enabled: Any
    track: Any
    image_vision_model: str = ""
    run_budget: Optional[RunBudget] = None

    is_update: bool = False
    candidate_names: List[str] = field(default_factory=list)
    selected_name_set: Set[str] = field(default_factory=set)
    last_updated: str = ""
    max_candidates: Optional[int] = None
    target_no_info: bool = False
    refine_iters: int = 1
    resume_partial: bool = False
    continue_incomplete_work: bool = False

    @property
    def prefix(self) -> str:
        """Log prefix distinguishing an update run from a fresh one.

        Derived rather than passed. It used to be computed in
        ``_run_shared_phases`` and handed to every phase, which meant a caller
        could pass a prefix that contradicted ``is_update``.
        """
        return "Update Phase" if self.is_update else "Phase"
