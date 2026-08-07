"""The pipeline step list is consumed by several tables that must cover it.

`PIPELINE_STEP_ORDER` is canonical, but labels, weights, the runner's enum and
the repair planner's cost model each keep their own keyed copy. Every one of
them degrades silently when a step is missing rather than raising, so these
tests assert coverage rather than contents — they keep working when a step is
added and fail only when a table was not updated with it.

The TypeScript mirrors are covered separately by `scripts/check_type_sync.py`.
"""

from pipeline_client.backend.models import ALL_STEPS, STEP_LABELS, STEP_WEIGHTS, PipelineStep
from shared import repair_planner
from shared.pipeline_config import (
    DEFAULT_UPDATE_PIPELINE_STEPS,
    PIPELINE_STEP_IDS,
    PIPELINE_STEP_LABELS,
    PIPELINE_STEP_ORDER,
    PIPELINE_STEP_WEIGHTS,
)


def test_forecast_step_runs_after_polling_before_voter_resources():
    assert PIPELINE_STEP_ORDER.index("polling") < PIPELINE_STEP_ORDER.index("forecast")
    assert PIPELINE_STEP_ORDER.index("forecast") < PIPELINE_STEP_ORDER.index("voter_resources")


def test_pipeline_step_weights_total_100():
    assert sum(PIPELINE_STEP_WEIGHTS.values()) == 100
    assert PIPELINE_STEP_WEIGHTS["forecast"] == 4


def test_step_order_has_no_duplicates():
    """Guards the assertions below, which compare against a set."""
    assert len(PIPELINE_STEP_ORDER) == len(set(PIPELINE_STEP_ORDER))
    assert PIPELINE_STEP_IDS == set(PIPELINE_STEP_ORDER)


def test_runner_enum_matches_the_canonical_order():
    """`AgentHandler` filters requested steps through this enum:

        enabled_steps = [s for s in raw if s in {e.value for e in PipelineStep}]

    so a step present in PIPELINE_STEP_ORDER but absent from the enum is dropped
    from the run without an error. The run reports success having skipped it.
    """
    assert [step.value for step in PipelineStep] == list(PIPELINE_STEP_ORDER)


def test_every_step_has_a_label_and_a_weight():
    """A step missing from either table renders blank or contributes no progress."""
    assert set(PIPELINE_STEP_LABELS) == set(PIPELINE_STEP_ORDER)
    assert set(PIPELINE_STEP_WEIGHTS) == set(PIPELINE_STEP_ORDER)


def test_backend_tables_are_the_shared_ones():
    """Guards against someone reintroducing a hand-written copy in backend.models."""
    assert ALL_STEPS == list(PIPELINE_STEP_ORDER)
    assert STEP_LABELS == PIPELINE_STEP_LABELS
    assert STEP_WEIGHTS == PIPELINE_STEP_WEIGHTS


def test_default_update_steps_are_real_steps():
    assert set(DEFAULT_UPDATE_PIPELINE_STEPS) <= set(PIPELINE_STEP_ORDER)


def test_every_step_carries_a_cost_estimate():
    """`repair_planner` prices a plan with `.get(step, 0.0)`, so an uncosted step
    is estimated at zero rather than flagged. Cost estimates gate whether a run
    is queued at all, and one that silently under-reports is worse than one that
    errors."""
    costed = (
        set(repair_planner._FIXED_STEP_COST_USD)
        | set(repair_planner._PER_CANDIDATE_COST_USD)
        # `issues` is priced per issue researched, not per step or per candidate.
        | {"issues"}
    )
    missing = set(PIPELINE_STEP_ORDER) - costed
    assert not missing, f"steps with no cost model, silently estimated at $0: {sorted(missing)}"

    unknown = costed - set(PIPELINE_STEP_ORDER)
    assert not unknown, f"cost model prices steps that do not exist: {sorted(unknown)}"


def test_a_step_is_never_priced_twice():
    """Being in both tables would add a fixed and a per-candidate charge."""
    overlap = set(repair_planner._FIXED_STEP_COST_USD) & set(repair_planner._PER_CANDIDATE_COST_USD)
    assert not overlap, f"steps priced both per-race and per-candidate: {sorted(overlap)}"
