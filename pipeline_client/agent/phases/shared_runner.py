"""Shared phase runner — images -> issues -> finance -> refinement -> polling ->
forecast -> voter_resources.

This is the sequence common to both a fresh discovery run (``fresh_run.py``)
and an update run (``update_run.py``); each phase's implementation lives in
its own module and is invoked here in order.

Every phase reads the same run state, so it is passed once as a
:class:`~.context.PhaseContext` rather than re-listed at each call. This file
used to be a hundred lines of argument threading, which meant any new
phase-level concern was an eight-file edit that touched nothing to do with the
concern itself.
"""

from .context import PhaseContext
from .finance import run_finance_phase
from .forecast import run_forecast_phase
from .image_resolution import run_image_resolution_phase
from .issues import run_issues_phase
from .polling import run_polling_phase
from .refinement import run_refinement_phase
from .voter_resources import run_voter_resources_phase

#: Run order is load-bearing: issues and finance populate the fields refinement
#: cleans up, and forecast reads the polling that precedes it.
_PHASES = (
    run_image_resolution_phase,
    run_issues_phase,
    run_finance_phase,
    run_refinement_phase,
    run_polling_phase,
    run_forecast_phase,
    run_voter_resources_phase,
)


async def _run_shared_phases(ctx: PhaseContext) -> None:
    """Run candidate research, polling, and voter-resource phases in order.

    Mutates ``ctx.race_json`` in place. Each phase decides for itself whether it
    is enabled (``ctx.step_enabled``) and records its own skip.
    """
    for phase in _PHASES:
        await phase(ctx)
