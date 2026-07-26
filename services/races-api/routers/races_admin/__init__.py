"""Race record CRUD, draft, publish, run-history, and chamber-forecast endpoints.

This package used to be a single ~870-line module. It is now split by concern:

    helpers.py    - shared reconciliation/status helpers used across the groups below
    records.py    - race record listing/get/delete, status recheck, run trigger
    forecasts.py  - chamber-level forecast draft/generate/publish
    drafts.py     - draft delete, publish, unpublish, batch publish
    race_runs.py  - per-race run history (list/get/cancel-or-delete a run)
    data.py       - full race JSON (published or draft) read endpoint

``router`` below is the combined APIRouter that ``main.py`` includes, exactly as
before. The include order matters for one pair of routes: the literal
``/api/races/chamber_forecasts/publish`` (forecasts) must be registered before
the parameterized ``/api/races/{race_id}/publish`` (drafts), or the latter would
shadow it by matching ``race_id="chamber_forecasts"``. This mirrors the original
single-file module's route declaration order.

A handful of private helpers are re-exported here (rather than only living in
``helpers.py``) because existing tests reach into this module directly, e.g.
``from routers import races_admin; races_admin._active_doc_is_fresh(...)`` and
``patch("routers.races_admin._assert_publishable_race", ...)``.
"""

from fastapi import APIRouter

# `drafts` reaches back into this package's own namespace (`routers.races_admin`) to
# call `_assert_publishable_race` at request time so that
# `patch("routers.races_admin._assert_publishable_race", ...)` keeps working. That
# lookup happens lazily inside request handlers, never at import time, so it is safe
# regardless of the relative order of these two import statements.
from . import data, drafts, forecasts, race_runs, records
from .forecasts import DEFAULT_CHAMBER_FORECAST_MODEL, GenerateForecastsRequest
from .helpers import (
    STALE_ACTIVE_RUN_SECONDS,
    _active_doc_is_fresh,
    _apply_catalog_view,
    _assert_publishable_race,
    _backfill_catalog_from_storage,
    _candidate_count_from_race_data,
    _catalog_update_from_storage,
    _clear_public_race_cache,
    _derive_inactive_storage_status,
    _derive_storage_status,
    _grade_from_race_data,
    _is_run_actually_active,
    _latest_activity_at,
    _newer_iso,
    _pipeline_run_stats,
    _published_race_update,
    _race_summary,
    _recheck_race_status,
    _run_completed_at,
    _run_is_terminal_or_missing,
    _self_heal_stale_active_race,
)

router = APIRouter()
router.include_router(records.router)
router.include_router(forecasts.router)
router.include_router(drafts.router)
router.include_router(race_runs.router)
router.include_router(data.router)

__all__ = [
    "router",
    "STALE_ACTIVE_RUN_SECONDS",
    "_active_doc_is_fresh",
    "_apply_catalog_view",
    "_assert_publishable_race",
    "_backfill_catalog_from_storage",
    "_candidate_count_from_race_data",
    "_catalog_update_from_storage",
    "_clear_public_race_cache",
    "_derive_inactive_storage_status",
    "_derive_storage_status",
    "_grade_from_race_data",
    "_is_run_actually_active",
    "_latest_activity_at",
    "_newer_iso",
    "_pipeline_run_stats",
    "_published_race_update",
    "_race_summary",
    "_recheck_race_status",
    "_run_completed_at",
    "_run_is_terminal_or_missing",
    "_self_heal_stale_active_race",
    "DEFAULT_CHAMBER_FORECAST_MODEL",
    "GenerateForecastsRequest",
]
