from pipeline_client.backend.race_manager import RaceManager, RaceRecord


def test_publish_then_metadata_keeps_published_status_with_stale_remote_reads(monkeypatch):
    """Publishing should stay published even if remote reads are briefly stale."""
    manager = RaceManager()

    # Simulate cloud mode so publish_race triggers synchronous flush behavior.
    manager._db = object()

    remote_record = RaceRecord(
        race_id="ga-senate-2026",
        status="draft",
        draft_updated_at="2026-04-04T00:00:00+00:00",
        created_at="2026-04-04T00:00:00+00:00",
        updated_at="2026-04-04T00:00:00+00:00",
    )

    def fake_get_race(race_id: str):
        _ = race_id
        return remote_record

    def fake_flush(record: RaceRecord):
        nonlocal remote_record
        remote_record = record

    # Keep saves in-process for deterministic assertions.
    monkeypatch.setattr(manager, "_save_race", lambda record: manager._local_races.__setitem__(record.race_id, record))
    monkeypatch.setattr(manager, "get_race", fake_get_race)
    monkeypatch.setattr(manager, "_flush_race_to_firestore", fake_flush)

    manager.publish_race("ga-senate-2026")
    manager.update_race_metadata(
        "ga-senate-2026",
        {
            "title": "Georgia Senate 2026",
            "updated_utc": "2026-04-04T00:01:00+00:00",
            "candidates": [{"name": "Candidate A"}],
        },
        active_draft=False,
    )

    final_record = manager._local_races["ga-senate-2026"]
    assert final_record.status == "published"
    assert final_record.published_at is not None
    assert final_record.draft_updated_at is None


def test_publish_race_clears_active_draft_state(monkeypatch):
    manager = RaceManager()
    manager._db = object()

    remote_record = RaceRecord(
        race_id="ar-senate-2026",
        status="draft",
        draft_updated_at="2026-04-04T00:00:00+00:00",
        created_at="2026-04-04T00:00:00+00:00",
        updated_at="2026-04-04T00:00:00+00:00",
    )

    def fake_get_race(race_id: str):
        _ = race_id
        return remote_record

    def fake_flush(record: RaceRecord):
        nonlocal remote_record
        remote_record = record

    monkeypatch.setattr(manager, "_save_race", lambda record: manager._local_races.__setitem__(record.race_id, record))
    monkeypatch.setattr(manager, "get_race", fake_get_race)
    monkeypatch.setattr(manager, "_flush_race_to_firestore", fake_flush)

    published = manager.publish_race("ar-senate-2026")

    assert published.status == "published"
    assert published.draft_updated_at is None


def test_update_metadata_only_does_not_set_draft_updated_at(monkeypatch):
    """_update_metadata_only should enrich fields but never touch draft_updated_at."""
    manager = RaceManager()

    existing = RaceRecord(
        race_id="mi-senate-2026",
        status="published",
        published_at="2026-04-04T00:00:00+00:00",
        draft_updated_at=None,
        created_at="2026-04-04T00:00:00+00:00",
        updated_at="2026-04-04T00:00:00+00:00",
    )

    monkeypatch.setattr(manager, "get_race", lambda race_id: existing)
    monkeypatch.setattr(
        manager,
        "_save_race",
        lambda record: manager._local_races.__setitem__(record.race_id, record),
    )

    manager._update_metadata_only(
        "mi-senate-2026",
        {
            "title": "Michigan Senate 2026",
            "updated_utc": "2026-04-04T01:00:00+00:00",
            "candidates": [{"name": "A"}, {"name": "B"}],
        },
    )

    result = manager._local_races["mi-senate-2026"]
    assert result.title == "Michigan Senate 2026"
    assert result.candidate_count == 2
    # Key assertion: draft_updated_at must remain None
    assert result.draft_updated_at is None


def test_recheck_status_no_draft_file_clears_draft_updated_at(monkeypatch, tmp_path):
    """recheck_status should not set draft_updated_at when no draft file exists."""
    from pipeline_client.backend.settings import settings

    monkeypatch.setattr(settings, "gcs_bucket", "")

    manager = RaceManager()

    existing = RaceRecord(
        race_id="mn-senate-2026",
        status="published",
        published_at="2026-04-04T00:00:00+00:00",
        draft_updated_at="2026-04-04T00:00:00+00:00",
        created_at="2026-04-04T00:00:00+00:00",
        updated_at="2026-04-04T00:00:00+00:00",
    )

    monkeypatch.setattr(manager, "get_race", lambda race_id: existing)
    monkeypatch.setattr(
        manager,
        "_save_race",
        lambda record: manager._local_races.__setitem__(record.race_id, record),
    )

    # Patch ROOT so file-system checks use tmp_path (no draft file, but published exists)
    import pipeline_client.backend.race_manager as rm_module

    monkeypatch.setattr(rm_module, "ROOT", tmp_path)
    pub_dir = tmp_path / "data" / "published"
    pub_dir.mkdir(parents=True)
    (pub_dir / "mn-senate-2026.json").write_text("{}")

    # No active runs
    from pipeline_client.backend import run_manager as run_mgr_module

    monkeypatch.setattr(run_mgr_module.run_manager, "list_active_runs", lambda: [])

    result = manager.recheck_status("mn-senate-2026")
    assert result.status == "published"
    # Without a draft file, draft_updated_at should be None
    assert result.draft_updated_at is None
