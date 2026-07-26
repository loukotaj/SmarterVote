"""Phase orchestration — discovery, issues, finance, refinement, iteration.

This package is a decomposition of what used to be a single ~1,700-line
``phases.py`` module. Each phase now lives in its own file:

- ``_common.py``           — shared constants/helpers (control-flow exception
                              handling, run-budget-bounded awaits, pipeline
                              unit-state bookkeeping).
- ``discovery.py``         — deterministic roster sanitization rules and the
                              advisory Ballotpedia roster sync.
- ``image_resolution.py``  — Phase 1b: candidate image URL verification.
- ``issues.py``            — Phase 2: per-candidate, per-issue sub-agent
                              research (sequential and concurrent variants).
- ``finance.py``           — Phase 2b: donor & voting-record research.
- ``refinement.py``        — Phase 3: per-candidate + meta refinement.
- ``polling.py``           — Phase 4: polling refresh.
- ``forecast.py``          — Phase 4b: race outcome forecast.
- ``voter_resources.py``   — Phase 5: voter resource verification.
- ``shared_runner.py``     — runs the phases above in order for both fresh
                              and update runs.
- ``fresh_run.py``         — ``_run_fresh``: discovery -> shared phases.
- ``update_run.py``        — ``_run_update``: roster sync/meta -> shared phases.
- ``iteration.py``         — ``_run_iteration_pass``: review-flag remediation.

This ``__init__`` re-exports the full public surface the previous flat
``phases.py`` module exposed, so every existing import site (production code
and tests, including tests that patch e.g.
``pipeline_client.agent.phases._agent_loop`` or
``pipeline_client.agent.phases._sync_ballotpedia_roster``) keeps working
unchanged. Phase modules that call one of those patched names do so via a
lazy ``from . import <name>`` *inside* the calling function (not a top-level
import) specifically so a monkeypatch applied to this package's namespace is
still honored no matter which submodule performs the call — this mirrors the
project's existing lazy-import convention for breaking circular dependencies.
"""

from .. import phase_state, roster  # noqa: F401 — re-exported for backward compat
from ..ballotpedia import lookup_election_page as _ballotpedia_election_lookup
from ..errors import PermanentProviderError, RetryableProviderError  # noqa: F401 — re-exported for backward compat
from ..handlers import _make_editing_handlers  # noqa: F401 — re-exported for backward compat
from ..images import resolve_candidate_images  # noqa: F401 — re-exported for backward compat
from ..llm import _agent_loop, _ensure_dict, _normalize_candidate
from ..market_data.kalshi import fetch_kalshi_market_signals
from ..model_registry import CHEAP_MODEL, DEFAULT_MODEL, NANO_MODEL  # noqa: F401 — re-exported for backward compat
from ..patches import (  # noqa: F401 — re-exported for backward compat
    _apply_candidate_patch,
    _apply_finance_patch,
    _apply_issue_patch,
    _apply_meta_patch,
    _apply_refine_patch,
    _deduplicate_donors,
    _summarize_existing_stances,
)
from ..prompts import (  # noqa: F401 — re-exported for backward compat
    CANONICAL_ISSUES,
    DISCOVERY_SYSTEM,
    DISCOVERY_USER,
    FINANCE_VOTING_SYSTEM,
    FINANCE_VOTING_USER,
    FORECAST_SYSTEM,
    FORECAST_USER,
    ISSUE_SUBAGENT_SYSTEM,
    ISSUE_SUBAGENT_USER,
    ITERATE_META_USER,
    ITERATE_SYSTEM,
    ITERATE_USER,
    POLLING_SYSTEM,
    POLLING_USER,
    REFINE_META_USER,
    REFINE_SYSTEM,
    REFINE_USER,
    ROSTER_SYNC_SYSTEM,
    ROSTER_SYNC_USER,
    ROSTER_VERIFY_SYSTEM,
    ROSTER_VERIFY_USER,
    UPDATE_ISSUE_SUBAGENT_SYSTEM,
    UPDATE_ISSUE_SUBAGENT_USER,
    UPDATE_META_SYSTEM,
    UPDATE_META_USER,
    VOTER_RESOURCES_SYSTEM,
    VOTER_RESOURCES_USER,
)
from ..review_flags import format_review_flags as _format_review_flags
from ..review_flags import has_actionable_flags as _has_actionable_flags
from ..run_budget import RunBudget, RunBudgetExceeded  # noqa: F401 — re-exported for backward compat
from ..selection import (  # noqa: F401 — re-exported for backward compat
    _candidate_info_score,
    _candidate_source_hints,
    _scale_iterations,
    _select_target_candidates,
    plan_candidate_work,
)
from ..tools import (  # noqa: F401 — re-exported for backward compat
    BACKGROUND_TOOLS,
    CANDIDATE_TOOLS,
    DESCRIPTION_TOOLS,
    FORECAST_TOOLS,
    ISSUE_TOOLS,
    POLLING_TOOLS,
    RACE_TOOLS,
    READ_PROFILE_TOOL,
    RECORD_TOOLS,
    REMOVE_CANDIDATE_TOOL,
    ROSTER_TOOLS,
    VOTER_RESOURCE_TOOLS,
)
from ..utils import make_logger  # noqa: F401 — re-exported for backward compat
from ..web_tools import _get_search_cache  # noqa: F401 — re-exported for backward compat
from ._common import (
    _CONTROL_FLOW_EXCEPTION_NAMES,
    PipelineWorkRemaining,
    RunFailureReason,
    _await_with_run_budget,
    _build_handoff_context,
    _candidate_name,
    _classify_exception,
    _detect_empty_finance_output,
    _is_control_flow_exception,
    _issue_stance_is_complete,
    _mark_pipeline_unit_complete,
    _pipeline_completed_units,
    _pipeline_issue_attempts,
    _race_identity_context,
    _record_step_failure,
    logger,
)
from .discovery import (
    _ROSTER_CAP,
    _TERM_LIMITED_NON_CANDIDATE_RE,
    _add_candidates_from_authoritative_roster,
    _backfill_source_timestamps,
    _candidate_matches_any,
    _candidate_roster_text,
    _cap_roster,
    _names_likely_same,
    _norm_name_for_match,
    _normalize_candidate_entries,
    _party_tag,
    _reconcile_candidates_with_authoritative_roster,
    _remove_inactive_candidates,
    _remove_ineligible_officeholders,
    _remove_known_ineligible_candidates,
    _sanitize_roster,
    _sync_ballotpedia_roster,
)
from .fresh_run import _run_fresh
from .issues import _research_issue_unit, _run_issue_research_for_candidate
from .iteration import _run_iteration_pass
from .shared_runner import _run_shared_phases
from .update_run import _run_update

__all__ = [
    "PipelineWorkRemaining",
    "_run_fresh",
    "_run_update",
    "_run_shared_phases",
    "_run_iteration_pass",
    "_run_issue_research_for_candidate",
    "_research_issue_unit",
    "_sanitize_roster",
    "_sync_ballotpedia_roster",
    "_candidate_source_hints",
    "_has_actionable_flags",
    "_scale_iterations",
    "_select_target_candidates",
]
