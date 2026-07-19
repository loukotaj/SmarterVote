import asyncio
from unittest.mock import MagicMock

import pytest

from pipeline_client.backend.pipeline_metrics import PipelineMetricsStore


class _AsyncDocs:
    def __init__(self, docs):
        self._docs = iter(docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._docs)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


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


@pytest.mark.asyncio
async def test_firestore_summary_uses_single_document_stream(monkeypatch, tmp_path):
    monkeypatch.delenv("FIRESTORE_PROJECT", raising=False)
    monkeypatch.setenv("PIPELINE_METRICS_DB_PATH", str(tmp_path / "metrics.db"))
    store = PipelineMetricsStore()
    collection = MagicMock()
    doc = MagicMock()
    doc.to_dict.return_value = {"status": "completed", "estimated_usd": 0.25}
    collection.stream.return_value = _AsyncDocs([doc])
    client = MagicMock()
    client.collection.return_value = collection
    store._client = client

    summary = await store._summary_firestore()

    assert summary["total_runs"] == 1
    assert summary["total_usd"] == pytest.approx(0.25)
    collection.stream.assert_called_once_with()
    assert not collection.count.called


@pytest.mark.asyncio
async def test_sqlite_metrics_support_concurrent_writers(monkeypatch, tmp_path):
    monkeypatch.delenv("FIRESTORE_PROJECT", raising=False)
    monkeypatch.setenv("PIPELINE_METRICS_DB_PATH", str(tmp_path / "metrics.db"))
    store = PipelineMetricsStore()

    await asyncio.gather(
        *[
            store.record_run(
                f"run-{index}",
                "az-senate-2026",
                {"estimated_usd": 0.01, "duration_s": 1.0},
                candidate_count=2,
            )
            for index in range(20)
        ]
    )

    records = await store.get_recent(limit=50)
    assert len(records) == 20
    assert {record["run_id"] for record in records} == {f"run-{index}" for index in range(20)}
