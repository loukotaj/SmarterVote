"""Phase orchestration — discovery, issues, finance, refinement, iteration.

Each phase lives in its own module:

- ``_common.py``           — shared helpers (control-flow exception handling,
                              run-budget-bounded awaits, unit-state bookkeeping).
- ``context.py``           — ``PhaseContext``: the per-run state every phase reads.
- ``discovery.py``         — deterministic roster sanitization and the advisory
                              Ballotpedia roster sync.
- ``image_resolution.py``  — Phase 1b: candidate image URL verification.
- ``issues.py``            — Phase 2: per-candidate, per-issue sub-agent research.
- ``finance.py``           — Phase 2b: donor & voting-record research.
- ``refinement.py``        — Phase 3: per-candidate + meta refinement.
- ``polling.py``           — Phase 4: polling refresh.
- ``forecast.py``          — Phase 4b: race outcome forecast.
- ``voter_resources.py``   — Phase 5: voter resource verification.
- ``shared_runner.py``     — runs the phases above in order for fresh and update runs.
- ``fresh_run.py``         — ``_run_fresh``: discovery -> shared phases.
- ``update_run.py``        — ``_run_update``: roster sync/meta -> shared phases.
- ``iteration.py``         — ``_run_iteration_pass``: review-flag remediation.

This module deliberately exports only two things:

**What callers outside the package use.** ``agent.py`` drives runs through
``_run_fresh``/``_run_update`` and a handful of helpers; those are re-exported
here so it has one import site.

**The monkeypatch seam.** Phase modules reach ``_agent_loop``,
``_sync_ballotpedia_roster``, ``_candidate_source_hints``,
``_ballotpedia_election_lookup`` and ``fetch_kalshi_market_signals`` through a
lazy ``from . import <name>`` *inside* the calling function, not a top-level
import. That indirection is what lets a test patch
``pipeline_client.agent.phases.<name>`` and have every submodule honour it. Those
five names must stay bound here or the patches silently stop taking effect —
tests would still pass while exercising the real implementation.

It used to re-export 110 names for backward compatibility. 100 of them were
referenced nowhere, which made this file read as the package's API when it was
mostly noise, and left three importable spellings for the same helper. Import
from the owning module instead.
"""

# --- the monkeypatch seam: patched as pipeline_client.agent.phases.<name> ---
from ..ballotpedia import lookup_election_page as _ballotpedia_election_lookup
from ..llm import _agent_loop
from ..market_data.kalshi import fetch_kalshi_market_signals

# --- the surface agent.py and tests import from this package ---
from ..review_flags import flagged_fields as _flagged_fields
from ..review_flags import format_review_flags as _format_review_flags
from ..review_flags import has_actionable_flags as _has_actionable_flags
from ..selection import _candidate_source_hints, _scale_iterations, _select_target_candidates
from ._common import PipelineWorkRemaining
from .discovery import (
    _add_candidates_from_authoritative_roster,
    _cap_roster,
    _reconcile_candidates_with_authoritative_roster,
    _remove_known_ineligible_candidates,
    _sanitize_roster,
    _sync_ballotpedia_roster,
)
from .fresh_run import _run_fresh
from .issues import _research_issue_unit
from .iteration import _run_iteration_pass
from .shared_runner import _run_shared_phases
from .update_run import _run_update

__all__ = [
    "PipelineWorkRemaining",
    "_add_candidates_from_authoritative_roster",
    "_format_review_flags",
    "_reconcile_candidates_with_authoritative_roster",
    "_agent_loop",
    "_ballotpedia_election_lookup",
    "_candidate_source_hints",
    "_cap_roster",
    "_flagged_fields",
    "_has_actionable_flags",
    "_remove_known_ineligible_candidates",
    "_research_issue_unit",
    "_run_fresh",
    "_run_iteration_pass",
    "_run_shared_phases",
    "_run_update",
    "_sanitize_roster",
    "_scale_iterations",
    "_select_target_candidates",
    "_sync_ballotpedia_roster",
    "fetch_kalshi_market_signals",
]
