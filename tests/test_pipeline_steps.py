from shared.pipeline_config import PIPELINE_STEP_ORDER, PIPELINE_STEP_WEIGHTS


def test_forecast_step_runs_after_polling_before_voter_resources():
    assert PIPELINE_STEP_ORDER.index("polling") < PIPELINE_STEP_ORDER.index("forecast")
    assert PIPELINE_STEP_ORDER.index("forecast") < PIPELINE_STEP_ORDER.index("voter_resources")


def test_pipeline_step_weights_total_100():
    assert sum(PIPELINE_STEP_WEIGHTS.values()) == 100
    assert PIPELINE_STEP_WEIGHTS["forecast"] == 4
