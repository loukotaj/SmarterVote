from pathlib import Path

from shared.config import LocalPaths


def test_local_paths_are_independent_of_working_directory(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    elsewhere = tmp_path / "elsewhere"
    repo_root.mkdir()
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    paths = LocalPaths.resolve(repo_root)

    assert paths.repo_root == repo_root.resolve()
    assert paths.drafts_dir == repo_root.resolve() / "data" / "drafts"
    assert paths.local_queue_path == repo_root.resolve() / "pipeline_client" / "queue.json"
    assert all(path.is_absolute() for path in paths.__dict__.values())


def test_local_paths_support_environment_override(monkeypatch, tmp_path):
    monkeypatch.setenv("SMARTERVOTE_REPO_ROOT", str(tmp_path))

    paths = LocalPaths.resolve()

    assert paths.repo_root == Path(tmp_path).resolve()
    assert paths.metrics_db_path == Path(tmp_path).resolve() / "data" / "pipeline_metrics.db"
