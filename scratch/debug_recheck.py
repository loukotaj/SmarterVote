import os
import sys
from pathlib import Path

# Add root directory to python path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline_client.backend.race_manager import RaceManager, RaceRecord

def run_debug():
    manager = RaceManager()
    existing = RaceRecord(
        race_id="mn-senate-2026",
        status="published",
        published_at="2026-04-04T00:00:00+00:00",
        draft_updated_at="2026-04-04T00:00:00+00:00",
        created_at="2026-04-04T00:00:00+00:00",
        updated_at="2026-04-04T00:00:00+00:00",
    )
    manager._local_races[existing.race_id] = existing

    # Mock ROOT to a temp path
    tmp_path = Path("C:/Users/jacob/AppData/Local/Temp/pytest-of-jacob/pytest-279/test_recheck_status_no_draft_f0")
    if not tmp_path.exists():
        tmp_path.mkdir(parents=True)
    import pipeline_client.backend.race_manager as rm_module
    rm_module.ROOT = tmp_path

    pub_dir = tmp_path / "data" / "published"
    pub_dir.mkdir(parents=True, exist_ok=True)
    (pub_dir / "mn-senate-2026.json").write_text("{}")

    # Let's inspect recheck_status
    race_id = "mn-senate-2026"
    race = manager.get_race(race_id)

    # Local drafts check
    draft_path = rm_module.ROOT / "data" / "drafts" / f"{race_id}.json"
    has_local_draft = draft_path.exists()

    # GCS drafts check
    has_gcs_draft = False
    has_gcs_published = False
    try:
        from pipeline_client.backend.settings import settings
        gcs_bucket = settings.gcs_bucket
        print(f"DEBUG: settings.gcs_bucket = {gcs_bucket}")
        if gcs_bucket:
            from pipeline_client.backend.main import _get_gcs_client
            client = _get_gcs_client()
            print(f"DEBUG: client = {client}")
            if client is not None:
                bucket = client.bucket(gcs_bucket)
                has_gcs_draft = bucket.blob(f"drafts/{race_id}.json").exists()
                has_gcs_published = bucket.blob(f"races/{race_id}.json").exists()
    except Exception as e:
        print(f"DEBUG: GCS exception: {e}")

    has_local_published = (rm_module.ROOT / "data" / "published" / f"{race_id}.json").exists()

    has_any_draft = has_local_draft or has_gcs_draft
    print(f"DEBUG: has_local_draft={has_local_draft}, has_gcs_draft={has_gcs_draft}, has_any_draft={has_any_draft}")
    print(f"DEBUG: has_local_published={has_local_published}, has_gcs_published={has_gcs_published}")

    now = "2026-06-14T10:49:53"
    if has_local_published or has_gcs_published:
        published_at = (race.published_at if race else None) or now
        draft_at = ((race.draft_updated_at if race else None) or now) if has_any_draft else None
        print(f"DEBUG: draft_at={draft_at}")

    result = manager.recheck_status("mn-senate-2026")
    print(f"DEBUG: result.draft_updated_at = {result.draft_updated_at}")

if __name__ == "__main__":
    run_debug()
