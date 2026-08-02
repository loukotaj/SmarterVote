"""The roster adjudicator gates publication, so its failure modes matter more than its happy path.

Every test here mocks the provider. Whether the model gives *good* judgments is
what scripts/fixtures/roster_evidence exists for; this file covers the wiring:
fail-closed behaviour, parsing, caching, and the reproducibility settings.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from pipeline_client.agent import roster_adjudicator as adj


@pytest.fixture(autouse=True)
def _clear_cache():
    adj.clear_cache()
    yield
    adj.clear_cache()


def _reply(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _source(**overrides):
    source = {
        "url": "https://sos.ne.gov/candidates",
        "title": "Official Candidate List",
        "evidence": "District 2 — U.S. Representative: Jane Roe (D), John Doe (R)",
        "published_at": "2026-06-01",
    }
    source.update(overrides)
    return source


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# --- fail closed --------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("OpenRouter 403: key quota exhausted"),
        ConnectionError("connection refused"),
        ValueError("boom"),
    ],
)
def test_provider_failure_fails_closed(monkeypatch, exc):
    """An unreachable judge must reject, never wave evidence through."""

    async def _boom(*args, **kwargs):
        raise exc

    monkeypatch.setattr("pipeline_client.agent.llm._call_openrouter", _boom)
    verdict = _run(
        adj.adjudicate(claim=adj.Claim.MEMBERSHIP, subject="Jane Roe", contest="ne-house-02-2026", source=_source())
    )
    assert verdict.supports is False
    assert verdict.unavailable is True
    assert "fails closed" in verdict.reason


def test_timeout_fails_closed(monkeypatch):
    async def _hang(*args, **kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr("pipeline_client.agent.llm._call_openrouter", _hang)
    monkeypatch.setattr(adj, "ADJUDICATOR_TIMEOUT_SECONDS", 0.01)
    verdict = _run(
        adj.adjudicate(claim=adj.Claim.MEMBERSHIP, subject="Jane Roe", contest="ne-house-02-2026", source=_source())
    )
    assert verdict.supports is False
    assert verdict.unavailable is True


@pytest.mark.parametrize("content", ["", "I think probably yes", "{malformed", "{}", '{"reason": "no verdict field"}'])
def test_unparseable_reply_fails_closed(monkeypatch, content):
    async def _reply_with(*args, **kwargs):
        return _reply(content)

    monkeypatch.setattr("pipeline_client.agent.llm._call_openrouter", _reply_with)
    verdict = _run(
        adj.adjudicate(claim=adj.Claim.MEMBERSHIP, subject="Jane Roe", contest="ne-house-02-2026", source=_source())
    )
    assert verdict.supports is False
    assert verdict.unavailable is True


def test_unknown_claim_fails_closed():
    verdict = _run(adj.adjudicate(claim="not_a_real_claim", subject="X", contest="y-2026", source=_source()))
    assert verdict.supports is False
    assert verdict.unavailable is True


# --- parsing ------------------------------------------------------------------


@pytest.mark.parametrize(
    "content,expected",
    [
        ('{"supports": true, "reason": "names the district and cycle"}', True),
        ('{"supports": false, "reason": "wrong district"}', False),
        ('```json\n{"supports": true, "reason": "ok"}\n```', True),
        ('Here is my verdict: {"supports": false, "reason": "blocked page"} — done.', False),
    ],
)
def test_parses_verdict_shapes(monkeypatch, content, expected):
    async def _reply_with(*args, **kwargs):
        return _reply(content)

    monkeypatch.setattr("pipeline_client.agent.llm._call_openrouter", _reply_with)
    verdict = _run(
        adj.adjudicate(claim=adj.Claim.MEMBERSHIP, subject="Jane Roe", contest="ne-house-02-2026", source=_source())
    )
    assert verdict.supports is expected
    assert verdict.unavailable is False
    assert verdict.reason


def test_reason_is_preserved_verbatim(monkeypatch):
    """Generic errors are what caused the retry loops; the specific reason must survive."""

    async def _reply_with(*args, **kwargs):
        return _reply('{"supports": false, "reason": "names District 2 of the state legislature, not Congress"}')

    monkeypatch.setattr("pipeline_client.agent.llm._call_openrouter", _reply_with)
    verdict = _run(
        adj.adjudicate(claim=adj.Claim.MEMBERSHIP, subject="Jane Roe", contest="ne-house-02-2026", source=_source())
    )
    assert verdict.reason == "names District 2 of the state legislature, not Congress"


# --- reproducibility ----------------------------------------------------------


def test_requests_temperature_zero_and_pinned_model(monkeypatch):
    """A publish gate must not drift run to run, nor on a silent provider upgrade."""
    seen = {}

    async def _capture(messages, **kwargs):
        seen.update(kwargs)
        return _reply('{"supports": true, "reason": "ok"}')

    monkeypatch.setattr("pipeline_client.agent.llm._call_openrouter", _capture)
    _run(adj.adjudicate(claim=adj.Claim.MEMBERSHIP, subject="Jane Roe", contest="ne-house-02-2026", source=_source()))
    assert seen["temperature"] == 0.0
    assert seen["model"] == adj.ADJUDICATOR_MODEL
    # A floating alias would let the provider move the gate with no commit.
    assert any(char.isdigit() for char in adj.ADJUDICATOR_MODEL)


def test_pinned_model_accepts_a_temperature_parameter():
    """llm._call_openrouter drops temperature for nano tiers; a nano gate could not be pinned to 0."""
    assert "nano" not in adj.ADJUDICATOR_MODEL


def test_identical_claims_are_cached(monkeypatch):
    calls = {"n": 0}

    async def _count(*args, **kwargs):
        calls["n"] += 1
        return _reply('{"supports": true, "reason": "ok"}')

    monkeypatch.setattr("pipeline_client.agent.llm._call_openrouter", _count)

    async def _twice():
        kwargs = dict(claim=adj.Claim.MEMBERSHIP, subject="Jane Roe", contest="ne-house-02-2026", source=_source())
        return await adj.adjudicate(**kwargs), await adj.adjudicate(**kwargs)

    first, second = _run(_twice())
    assert calls["n"] == 1
    assert first.supports is second.supports


def test_failures_are_not_cached(monkeypatch):
    """A quota blip must not poison the gate for the rest of the run."""
    calls = {"n": 0}

    async def _fail_then_succeed(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("429")
        return _reply('{"supports": true, "reason": "ok"}')

    monkeypatch.setattr("pipeline_client.agent.llm._call_openrouter", _fail_then_succeed)

    async def _twice():
        kwargs = dict(claim=adj.Claim.MEMBERSHIP, subject="Jane Roe", contest="ne-house-02-2026", source=_source())
        return await adj.adjudicate(**kwargs), await adj.adjudicate(**kwargs)

    first, second = _run(_twice())
    assert first.supports is False and first.unavailable is True
    assert second.supports is True
    assert calls["n"] == 2


def test_different_claims_on_one_source_are_judged_separately(monkeypatch):
    calls = {"n": 0}

    async def _count(*args, **kwargs):
        calls["n"] += 1
        return _reply('{"supports": true, "reason": "ok"}')

    monkeypatch.setattr("pipeline_client.agent.llm._call_openrouter", _count)

    async def _both():
        source = _source()
        await adj.adjudicate(claim=adj.Claim.MEMBERSHIP, subject="Jane Roe", contest="x-2026", source=source)
        await adj.adjudicate(claim=adj.Claim.COMPLETENESS, subject="Jane Roe", contest="x-2026", source=source)

    _run(_both())
    assert calls["n"] == 2


# --- prompt construction ------------------------------------------------------


def test_prompt_carries_evidence_and_never_the_desired_answer(monkeypatch):
    """The judge must not be told what the caller hopes to hear."""
    captured = {}

    async def _capture(messages, **kwargs):
        captured["system"] = messages[0]["content"]
        captured["user"] = messages[1]["content"]
        return _reply('{"supports": true, "reason": "ok"}')

    monkeypatch.setattr("pipeline_client.agent.llm._call_openrouter", _capture)
    _run(
        adj.adjudicate(
            claim=adj.Claim.MEMBERSHIP,
            subject="Jane Roe",
            contest="ne-house-02-2026",
            source=_source(evidence="Jane Roe is listed for U.S. House District 2"),
        )
    )
    assert "Jane Roe is listed for U.S. House District 2" in captured["user"]
    assert "ne-house-02-2026" in captured["user"]
    for leak in ("accept", "approve", "should pass", "the caller wants"):
        assert leak not in captured["user"].casefold()
    assert "outside knowledge" in captured["system"]


def test_missing_evidence_is_stated_not_hidden(monkeypatch):
    captured = {}

    async def _capture(messages, **kwargs):
        captured["user"] = messages[1]["content"]
        return _reply('{"supports": false, "reason": "no evidence"}')

    monkeypatch.setattr("pipeline_client.agent.llm._call_openrouter", _capture)
    _run(adj.adjudicate(claim=adj.Claim.MEMBERSHIP, subject="X", contest="y-2026", source=_source(evidence="")))
    assert "no evidence text was supplied" in captured["user"]


# --- batch --------------------------------------------------------------------


def test_adjudicate_sources_keys_by_url(monkeypatch):
    async def _ok(*args, **kwargs):
        return _reply('{"supports": true, "reason": "ok"}')

    monkeypatch.setattr("pipeline_client.agent.llm._call_openrouter", _ok)
    sources = [_source(url="https://a.gov/1"), _source(url="https://b.gov/2", evidence="different text")]
    verdicts = _run(
        adj.adjudicate_sources(claim=adj.Claim.MEMBERSHIP, subject="Jane Roe", contest="ne-house-02-2026", sources=sources)
    )
    assert set(verdicts) == {"https://a.gov/1", "https://b.gov/2"}
    assert all(record["supports"] for record in verdicts.values())
    assert all(record["model"] == adj.ADJUDICATOR_MODEL for record in verdicts.values())


def test_adjudicate_sources_skips_urlless_sources(monkeypatch):
    async def _ok(*args, **kwargs):
        return _reply('{"supports": true, "reason": "ok"}')

    monkeypatch.setattr("pipeline_client.agent.llm._call_openrouter", _ok)
    verdicts = _run(
        adj.adjudicate_sources(claim=adj.Claim.MEMBERSHIP, subject="X", contest="y-2026", sources=[{"evidence": "no url"}])
    )
    assert verdicts == {}


def test_verdict_record_is_persistable():
    """The record is written onto the source, so it must be plain JSON-safe data."""
    import json

    record = adj.Verdict(supports=False, reason="wrong district").to_record()
    assert json.loads(json.dumps(record)) == record
    assert record["reason"] == "wrong district"
