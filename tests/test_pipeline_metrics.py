import pytest

from pipeline_client.backend.pipeline_metrics import PipelineMetricsStore


@pytest.mark.asyncio
async def test_pipeline_metrics_persists_and_summarizes_provider_cost(monkeypatch, tmp_path):
    monkeypatch.delenv("FIRESTORE_PROJECT", raising=False)
    monkeypatch.setenv("PIPELINE_METRICS_DB_PATH", str(tmp_path / "metrics.db"))
    store = PipelineMetricsStore()

    await store.record_run(
        "run-exact",
        "ar-senate-2026",
        {
            "model": "openai/gpt-5.4-mini",
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "estimated_usd": 0.02,
            "cost_usd": 0.01234567,
            "cost_source": "provider",
            "model_breakdown": {},
            "duration_s": 1.5,
        },
        candidate_count=2,
        cheap_mode=True,
    )

    records = await store.get_recent()
    summary = await store.get_summary()

    assert records[0]["cost_usd"] == pytest.approx(0.01234567)
    assert records[0]["cost_source"] == "provider"
    assert summary["total_usd"] == pytest.approx(0.0123)
    assert summary["avg_cheap_usd"] == pytest.approx(0.0123)
