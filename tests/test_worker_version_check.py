"""Tests for worker commit version checking and staleness warnings."""

from __future__ import annotations

from shared.run_health import RunFailureReason, check_worker_version_staleness


def test_check_worker_version_staleness_cloud_runner() -> None:
    res = check_worker_version_staleness(runner="cloud_run")
    assert res["is_stale"] is False
    assert res["runner"] == "cloud_run"


def test_check_worker_version_staleness_matching_commits() -> None:
    res = check_worker_version_staleness(
        runner="local",
        worker_commit="abc123456789",
        repo_commit="abc123456789",
    )
    assert res["is_stale"] is False
    assert res["worker_commit"] == "abc1234"
    assert res["repo_commit"] == "abc1234"


def test_check_worker_version_staleness_different_commits() -> None:
    res = check_worker_version_staleness(
        runner="local",
        worker_commit="abc123456789",
        repo_commit="def567890123",
    )
    assert res["is_stale"] is True
    assert res["worker_commit"] == "abc1234"
    assert res["repo_commit"] == "def5678"
    assert "docker compose" in res["warning"]
    assert "abc1234" in res["warning"]
    assert "def5678" in res["warning"]


def test_stale_worker_failure_reason_enum() -> None:
    assert RunFailureReason.STALE_WORKER_VERSION.value == "stale_worker_version"


def test_unknown_worker_commit_is_not_reported_as_current(monkeypatch) -> None:
    """Regression: an unreported build commit used to be assumed equal to HEAD.

    Nothing stamped WORKER_GIT_COMMIT into the image, so every worker looked
    current and this check could never fire. A container built before several
    merged fixes then ran for hours, silently writing bad data.
    """
    monkeypatch.delenv("WORKER_GIT_COMMIT", raising=False)
    monkeypatch.delenv("GIT_COMMIT", raising=False)

    res = check_worker_version_staleness(runner="local", repo_commit="def567890123")

    assert res["is_stale"] is not False, "unknown provenance must not read as current"
    assert res["worker_commit"] is None
    assert "did not report the commit" in res["warning"]
    assert "docker compose" in res["warning"]


def test_worker_commit_from_environment_is_used(monkeypatch) -> None:
    monkeypatch.setenv("WORKER_GIT_COMMIT", "abc123456789")

    res = check_worker_version_staleness(runner="local", repo_commit="def567890123")

    assert res["is_stale"] is True
    assert res["worker_commit"] == "abc1234"
