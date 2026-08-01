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
