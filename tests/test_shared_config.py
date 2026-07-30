from pathlib import Path

from shared.config import LocalPaths
from shared.models import CanonicalIssue
from shared.pipeline_config import CANONICAL_ISSUE_COUNT, PipelineRuntimeConfig, normalize_review_providers


def test_local_paths_are_independent_of_working_directory(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    elsewhere = tmp_path / "elsewhere"
    repo_root.mkdir()
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    paths = LocalPaths.resolve(repo_root)

    assert paths.repo_root == repo_root.resolve()
    assert paths.drafts_dir == repo_root.resolve() / "data" / "drafts"
    assert all(path.is_absolute() for path in paths.__dict__.values())


def test_local_paths_support_environment_override(monkeypatch, tmp_path):
    monkeypatch.setenv("SMARTERVOTE_REPO_ROOT", str(tmp_path))

    paths = LocalPaths.resolve()

    assert paths.repo_root == Path(tmp_path).resolve()
    assert paths.metrics_db_path == Path(tmp_path).resolve() / "data" / "pipeline_metrics.db"


def test_pipeline_runtime_config_derives_issue_thresholds_from_canonical_issues(monkeypatch):
    monkeypatch.delenv("PIPELINE_QUALITY_CRITICAL_ISSUE_STANCES", raising=False)
    monkeypatch.delenv("PIPELINE_QUALITY_WARNING_ISSUE_STANCES", raising=False)

    config = PipelineRuntimeConfig.from_env()

    assert CANONICAL_ISSUE_COUNT == len(CanonicalIssue)
    assert config.quality_critical_issue_stances == len(CanonicalIssue) // 2
    assert config.quality_warning_issue_stances == (len(CanonicalIssue) * 2) // 3


def test_runtime_config_bounds_review_cycles_and_issue_concurrency(monkeypatch):
    monkeypatch.setenv("PIPELINE_MAX_REVIEW_CYCLES", "99")
    monkeypatch.setenv("PIPELINE_ISSUE_CONCURRENCY", "99")

    config = PipelineRuntimeConfig.from_env()

    assert config.max_review_cycles == 3
    assert config.issue_concurrency == 8


def test_runtime_config_bounds_search_and_token_ceilings(monkeypatch):
    monkeypatch.setenv("PIPELINE_MAX_SEARCH_CALLS", "99999")
    monkeypatch.setenv("PIPELINE_MAX_TOTAL_TOKENS", "999999999")

    config = PipelineRuntimeConfig.from_env()

    assert config.max_search_calls == 5000
    assert config.max_total_tokens == 50_000_000


def test_review_providers_cannot_be_empty():
    try:
        normalize_review_providers([])
    except ValueError as exc:
        assert "review_providers cannot be empty" in str(exc)
    else:
        raise AssertionError("empty review provider lists must fail validation")
