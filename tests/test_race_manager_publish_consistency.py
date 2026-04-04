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
    )

    final_record = manager._local_races["ga-senate-2026"]
    assert final_record.status == "published"
    assert final_record.published_at is not None
