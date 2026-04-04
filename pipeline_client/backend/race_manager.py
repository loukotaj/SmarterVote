"""
Unified race management service.

Each race is the central entity. Runs, queue status, draft/published state, and
analytics are all attributes of a race record stored in Firestore (collection: "races").

Runs are stored as a subcollection: races/{race_id}/runs/{run_id}.

Queue is simply races with status="queued" ordered by queue_position — no separate
collection needed.

Storage strategy mirrors run_manager.py:
- Cloud Run: Firestore required (fail-fast if missing)
- Local dev: in-memory dict fallback
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from .models import RunInfo, RunStatus

logger = logging.getLogger(__name__)

_COLLECTION = "races"
ROOT = Path(__file__).resolve().parents[2]


class RaceStatus(str):
    EMPTY = "empty"
    QUEUED = "queued"
    RUNNING = "running"
    DRAFT = "draft"
    PUBLISHED = "published"
    FAILED = "failed"


class RaceRecord(BaseModel):
    race_id: str
    title: Optional[str] = None
    office: Optional[str] = None
    jurisdiction: Optional[str] = None
    election_date: Optional[str] = None

    # Status
    status: str = "empty"  # empty | queued | running | draft | published | failed
    published_at: Optional[str] = None
    draft_updated_at: Optional[str] = None

    # Quality
    candidate_count: int = 0
    quality_score: Optional[int] = None
    freshness: Optional[str] = None  # fresh | recent | aging | stale

    # Pipeline / Queue
    queue_position: Optional[int] = None
    queue_options: Optional[Dict[str, Any]] = None
    current_run_id: Optional[str] = None
    last_run_id: Optional[str] = None
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None
    total_runs: int = 0

    # Analytics
    requests_24h: int = 0
    last_accessed: Optional[str] = None

    # Timestamps
    created_at: str = ""
    updated_at: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_freshness(updated_utc: Optional[str]) -> str:
    if not updated_utc:
        return "stale"
    try:
        diff = datetime.now(timezone.utc) - datetime.fromisoformat(updated_utc.replace("Z", "+00:00"))
        days = diff.days
    except Exception:
        return "stale"
    if days <= 7:
        return "fresh"
    if days <= 14:
        return "recent"
    if days <= 30:
        return "aging"
    return "stale"


def _compute_quality(candidate_count: int) -> int:
    return min(50 + candidate_count * 10, 100)


class RaceManager:
    """Manages the unified race lifecycle: metadata, queue, runs, publish."""

    def __init__(self):
        self._db: Optional[Any] = None
        self._local_races: Dict[str, RaceRecord] = {}
        self._local_runs: Dict[str, Dict[str, RunInfo]] = {}  # race_id -> {run_id: RunInfo}
        self._deleted_run_ids: set = set()  # track deleted runs to prevent ghost Firestore writes
        self._init_store()

    def _init_store(self) -> None:
        project = os.getenv("FIRESTORE_PROJECT")
        is_cloud_run = bool(os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_SERVICE"))

        if not project:
            if is_cloud_run:
                raise RuntimeError(
                    "Cloud Run detected but FIRESTORE_PROJECT is not set. "
                    "RaceManager requires Firestore for durability."
                )
            logger.info("RaceManager: FIRESTORE_PROJECT not set — using in-memory (local dev)")
            return
        try:
            from google.cloud import firestore  # type: ignore

            self._db = firestore.Client(project=project)
            logger.info("RaceManager: using Firestore project=%s collection=%s", project, _COLLECTION)
        except ImportError:
            if is_cloud_run:
                raise RuntimeError("Cloud Run detected but google-cloud-firestore not installed.")
            logger.warning("google-cloud-firestore not installed; using in-memory")
        except Exception as e:
            if is_cloud_run:
                raise RuntimeError(f"Cloud Run: failed to init Firestore: {e}")
            logger.exception("Firestore init failed; using in-memory")

    # ── Race CRUD ─────────────────────────────────────────────────────────

    def get_race(self, race_id: str) -> Optional[RaceRecord]:
        # Always prefer local cache — it is updated synchronously on every write,
        # so it is always at least as fresh as Firestore (which is written async).
        if race_id in self._local_races:
            return self._local_races[race_id]
        if self._db is not None:
            try:
                doc = self._db.collection(_COLLECTION).document(race_id).get()
                if doc.exists:
                    record = RaceRecord(**(doc.to_dict() or {}))
                    self._local_races[race_id] = record  # populate cache on Firestore hit
                    return record
            except Exception:
                logger.exception("Firestore get failed for race %s", race_id)
            return None
        return None

    def list_races(self, limit: int = 200) -> List[RaceRecord]:
        # Use local cache if available (populated by hydration and all writes)
        if self._local_races:
            return sorted(self._local_races.values(), key=lambda r: r.race_id)[:limit]
        if self._db is not None:
            try:
                docs = self._db.collection(_COLLECTION).limit(limit).stream()
                races = []
                for doc in docs:
                    try:
                        races.append(RaceRecord(**(doc.to_dict() or {})))
                    except Exception:
                        pass
                return sorted(races, key=lambda r: r.race_id)
            except Exception:
                logger.exception("Firestore list_races failed")
                return []
        return []

    def upsert_race(self, race_id: str, **fields) -> RaceRecord:
        """Create or update a race record. Only provided fields are changed."""
        now = _now_iso()
        existing = self.get_race(race_id)

        if existing:
            data = existing.model_dump()
            data.update({k: v for k, v in fields.items() if v is not None or k in fields})
            data["updated_at"] = now
            record = RaceRecord(**data)
        else:
            record = RaceRecord(race_id=race_id, created_at=now, updated_at=now, **fields)

        self._save_race(record)
        return record

    def delete_race(self, race_id: str) -> bool:
        # Remove from local cache immediately
        in_cache = race_id in self._local_races
        self._local_races.pop(race_id, None)
        self._local_runs.pop(race_id, None)
        if self._db is not None:
            try:
                doc_ref = self._db.collection(_COLLECTION).document(race_id)
                if not doc_ref.get().exists:
                    return in_cache  # was in cache but not yet in Firestore
                # Delete subcollection runs first
                runs_ref = doc_ref.collection("runs")
                for run_doc in runs_ref.stream():
                    run_doc.reference.delete()
                doc_ref.delete()
                return True
            except Exception:
                logger.exception("Firestore delete failed for race %s", race_id)
                return False
        return in_cache

    # ── Queue Operations ──────────────────────────────────────────────────

    def queue_races(self, race_ids: List[str], options: Optional[Dict[str, Any]] = None) -> List[RaceRecord]:
        """Queue multiple races for pipeline processing. Returns updated records."""
        # Find max queue position
        existing = self.list_races(500)
        max_pos = max((r.queue_position or 0 for r in existing if r.status == "queued"), default=0)

        results = []
        for i, race_id in enumerate(race_ids):
            existing_race = self.get_race(race_id)
            if existing_race and existing_race.status in ("queued", "running"):
                results.append(existing_race)  # already active
                continue

            record = self.upsert_race(
                race_id,
                status="queued",
                queue_position=max_pos + i + 1,
                queue_options=options or {},
            )
            results.append(record)
        return results

    def dequeue_race(self, race_id: str) -> Optional[RaceRecord]:
        """Remove a race from queue (set status back to previous meaningful state)."""
        race = self.get_race(race_id)
        if not race or race.status not in ("queued",):
            return None

        new_status = "published" if race.published_at else ("draft" if race.draft_updated_at else "empty")
        return self.upsert_race(
            race_id,
            status=new_status,
            queue_position=None,
            queue_options=None,
        )

    def cancel_race(self, race_id: str) -> Optional[RaceRecord]:
        """Cancel a queued or running race."""
        race = self.get_race(race_id)
        if not race or race.status not in ("queued", "running"):
            return None

        new_status = "published" if race.published_at else ("draft" if race.draft_updated_at else "failed")
        return self.upsert_race(
            race_id,
            status=new_status,
            queue_position=None,
            queue_options=None,
            current_run_id=None,
        )

    def get_queue(self) -> List[RaceRecord]:
        """Get all queued races, ordered by queue_position."""
        all_races = self.list_races(500)
        queued = [r for r in all_races if r.status in ("queued", "running")]
        return sorted(queued, key=lambda r: r.queue_position or 999999)

    def get_next_queued(self) -> Optional[RaceRecord]:
        """Get next race to process (status=queued, lowest queue_position)."""
        queue = self.get_queue()
        for r in queue:
            if r.status == "queued":
                return r
        return None

    def has_running(self) -> bool:
        all_races = self.list_races(500)
        return any(r.status == "running" for r in all_races)

    # ── Run Lifecycle ─────────────────────────────────────────────────────

    def start_run(self, race_id: str, run_id: str) -> RaceRecord:
        """Mark race as running with the given run_id."""
        return self.upsert_race(
            race_id,
            status="running",
            current_run_id=run_id,
            queue_position=None,
        )

    def complete_run(self, race_id: str, run_id: str, artifact_id: Optional[str] = None) -> RaceRecord:
        """Mark a run as completed. Sets race to draft (not published — admin must publish)."""
        now = _now_iso()
        race = self.get_race(race_id)
        total = (race.total_runs if race else 0) + 1
        # If it was published before, keep published status
        new_status = "published" if (race and race.published_at) else "draft"

        return self.upsert_race(
            race_id,
            status=new_status,
            current_run_id=None,
            last_run_id=run_id,
            last_run_at=now,
            last_run_status="completed",
            draft_updated_at=now,
            total_runs=total,
            queue_options=None,
        )

    def fail_run(self, race_id: str, run_id: str, error: str) -> RaceRecord:
        """Mark a run as failed."""
        now = _now_iso()
        race = self.get_race(race_id)
        total = (race.total_runs if race else 0) + 1
        # Preserve published/draft if applicable
        new_status = "published" if (race and race.published_at) else ("draft" if (race and race.draft_updated_at) else "failed")

        return self.upsert_race(
            race_id,
            status=new_status,
            current_run_id=None,
            last_run_id=run_id,
            last_run_at=now,
            last_run_status="failed",
            total_runs=total,
            queue_options=None,
        )

    def recheck_status(self, race_id: str) -> RaceRecord:
        """Re-derive race status from actual storage (GCS/local files + active runs).

        Safe to call at any time.  Used to recover races stuck in 'running'
        after a process crash or serialisation error.
        """
        from .run_manager import run_manager as _run_manager

        race = self.get_race(race_id)

        # If there is a genuinely active run for this race, don't touch status.
        active = [r for r in _run_manager.list_active_runs() if r.payload.get("race_id") == race_id]
        if active:
            return race or self.upsert_race(race_id, status="running")

        # Check for a local draft file
        draft_path = ROOT / "data" / "drafts" / f"{race_id}.json"
        has_local_draft = draft_path.exists()

        # Check GCS
        has_gcs_draft = False
        has_gcs_published = False
        try:
            from .settings import settings
            gcs_bucket = settings.gcs_bucket
            if gcs_bucket:
                from google.cloud import storage as _gcs  # type: ignore
                client = _gcs.Client()
                bucket = client.bucket(gcs_bucket)
                has_gcs_draft = bucket.blob(f"drafts/{race_id}.json").exists()
                has_gcs_published = bucket.blob(f"races/{race_id}.json").exists()
        except Exception:
            logger.debug("GCS check during recheck failed (non-fatal)", exc_info=True)

        # Check local published
        pub_path = ROOT / "data" / "published" / f"{race_id}.json"
        has_local_published = pub_path.exists()

        now = _now_iso()
        if has_local_published or has_gcs_published:
            published_at = (race.published_at if race else None) or now
            return self.upsert_race(
                race_id,
                status="published",
                published_at=published_at,
                draft_updated_at=(race.draft_updated_at if race else None) or now,
                current_run_id=None,
            )
        if has_local_draft or has_gcs_draft:
            return self.upsert_race(
                race_id,
                status="draft",
                draft_updated_at=(race.draft_updated_at if race else None) or now,
                current_run_id=None,
            )
        # Nothing found: mark as empty (or failed if we had a run)
        had_run = race and race.last_run_id
        return self.upsert_race(
            race_id,
            status="failed" if had_run else "empty",
            current_run_id=None,
        )

    def publish_race(self, race_id: str) -> RaceRecord:
        """Mark race as published."""
        now = _now_iso()
        return self.upsert_race(race_id, status="published", published_at=now)

    def delete_draft(self, race_id: str) -> RaceRecord:
        """Clear draft state from race record. status becomes published (if published) or empty."""
        race = self.get_race(race_id)
        new_status = "published" if (race and race.published_at) else "empty"
        return self.upsert_race(race_id, status=new_status, draft_updated_at=None)

    def unpublish_race(self, race_id: str) -> RaceRecord:
        """Remove published status. Race becomes draft if draft exists, else empty."""
        race = self.get_race(race_id)
        new_status = "draft" if (race and race.draft_updated_at) else "empty"
        return self.upsert_race(race_id, status=new_status, published_at=None)

    def update_race_metadata(self, race_id: str, race_data: Dict[str, Any]) -> RaceRecord:
        """Update race metadata from RaceJSON content (e.g. after agent run or on hydration)."""
        candidates = race_data.get("candidates", [])
        candidate_count = len(candidates)
        quality = _compute_quality(candidate_count)
        updated_utc = race_data.get("updated_utc")
        freshness = _compute_freshness(updated_utc)

        return self.upsert_race(
            race_id,
            title=race_data.get("title"),
            office=race_data.get("office"),
            jurisdiction=race_data.get("jurisdiction"),
            election_date=race_data.get("election_date"),
            candidate_count=candidate_count,
            quality_score=quality,
            freshness=freshness,
            draft_updated_at=updated_utc,
        )

    def _update_metadata_only(self, race_id: str, race_data: Dict[str, Any]) -> None:
        """Update metadata fields on an existing race WITHOUT bumping updated_at.

        Used during hydration so server restarts don't make every race appear
        freshly modified.
        """
        existing = self.get_race(race_id)
        if not existing:
            return

        candidates = race_data.get("candidates", [])
        candidate_count = len(candidates)
        quality = _compute_quality(candidate_count)
        updated_utc = race_data.get("updated_utc")
        freshness = _compute_freshness(updated_utc)

        data = existing.model_dump()
        changes: Dict[str, Any] = {
            "title": race_data.get("title"),
            "office": race_data.get("office"),
            "jurisdiction": race_data.get("jurisdiction"),
            "election_date": race_data.get("election_date"),
            "candidate_count": candidate_count,
            "quality_score": quality,
            "freshness": freshness,
        }
        if updated_utc:
            changes["draft_updated_at"] = updated_utc

        data.update({k: v for k, v in changes.items() if v is not None})
        record = RaceRecord(**data)
        self._save_race(record)

    # ── Run Subcollection ─────────────────────────────────────────────────

    def save_run(self, race_id: str, run_info: RunInfo) -> None:
        """Save a run to the races/{race_id}/runs subcollection."""
        # Always update local cache immediately for consistent reads
        self._local_runs.setdefault(race_id, {})[run_info.run_id] = run_info

        if self._db is not None:
            data = run_info.model_dump(mode="json")
            data.pop("logs", None)
            threading.Thread(
                target=self._write_run_firestore,
                args=(race_id, run_info.run_id, data),
                daemon=True,
            ).start()

    def get_run(self, race_id: str, run_id: str) -> Optional[RunInfo]:
        # Check local cache first
        cached = self._local_runs.get(race_id, {}).get(run_id)
        if cached is not None:
            return cached
        if self._db is not None:
            try:
                doc = (
                    self._db.collection(_COLLECTION)
                    .document(race_id)
                    .collection("runs")
                    .document(run_id)
                    .get()
                )
                if doc.exists:
                    run = RunInfo(**(doc.to_dict() or {}))
                    self._local_runs.setdefault(race_id, {})[run_id] = run  # populate cache
                    return run
            except Exception:
                logger.exception("Firestore get_run failed for %s/%s", race_id, run_id)
            return None
        return None

    def list_runs(self, race_id: str, limit: int = 20) -> List[RunInfo]:
        # Use local cache if available for this race
        race_runs = self._local_runs.get(race_id)
        if race_runs is not None:
            runs = sorted(race_runs.values(), key=lambda r: r.started_at or datetime.min, reverse=True)
            return runs[:limit]
        if self._db is not None:
            try:
                from google.cloud.firestore import Query  # type: ignore

                docs = (
                    self._db.collection(_COLLECTION)
                    .document(race_id)
                    .collection("runs")
                    .order_by("started_at", direction=Query.DESCENDING)
                    .limit(limit)
                    .stream()
                )
                runs = []
                for doc in docs:
                    try:
                        run = RunInfo(**(doc.to_dict() or {}))
                        runs.append(run)
                        self._local_runs.setdefault(race_id, {})[run.run_id] = run  # populate cache
                    except Exception:
                        pass
                return runs
            except Exception:
                logger.exception("Firestore list_runs failed for %s", race_id)
                return []
        return []

    def delete_run(self, race_id: str, run_id: str) -> bool:
        # Remove from local cache immediately and track deletion to prevent ghost writes
        race_runs = self._local_runs.get(race_id, {})
        in_cache = run_id in race_runs
        race_runs.pop(run_id, None)
        self._deleted_run_ids.add(run_id)

        if self._db is not None:
            try:
                doc_ref = (
                    self._db.collection(_COLLECTION)
                    .document(race_id)
                    .collection("runs")
                    .document(run_id)
                )
                if doc_ref.get().exists:
                    doc_ref.delete()
                    return True
                return in_cache  # was in local cache but background write hadn't reached Firestore yet
            except Exception:
                logger.exception("Firestore delete_run failed for %s/%s", race_id, run_id)
                return in_cache
        return in_cache

    # ── Hydration ─────────────────────────────────────────────────────────

    def hydrate_from_files(self) -> int:
        """Populate race records from existing GCS/local JSON files.

        Scans published and draft directories. Only creates records for races
        that don't already exist in Firestore (idempotent).
        Returns count of new records created.
        """
        count = 0
        now = _now_iso()

        published_dir = ROOT / "data" / "published"
        drafts_dir = ROOT / "data" / "drafts"

        seen: Dict[str, Dict[str, Any]] = {}

        # Published races
        if published_dir.exists():
            for path in published_dir.glob("*.json"):
                try:
                    with path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    race_id = data.get("id", path.stem)
                    seen[race_id] = {"data": data, "published": True, "draft": False, "pub_utc": data.get("updated_utc")}
                except Exception:
                    logger.warning("Failed to read %s during hydration", path)

        # Draft races
        if drafts_dir.exists():
            for path in drafts_dir.glob("*.json"):
                try:
                    with path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    race_id = data.get("id", path.stem)
                    if race_id in seen:
                        seen[race_id]["draft"] = True
                        seen[race_id]["data"] = data  # draft is more recent
                    else:
                        seen[race_id] = {"data": data, "published": False, "draft": True}
                except Exception:
                    logger.warning("Failed to read %s during hydration", path)

        for race_id, info in seen.items():
            existing = self.get_race(race_id)
            if existing:
                # Update metadata without bumping updated_at (hydration only)
                self._update_metadata_only(race_id, info["data"])
                continue

            data = info["data"]
            candidates = data.get("candidates", [])
            updated_utc = data.get("updated_utc")

            status = "published" if info["published"] else "draft"
            record = RaceRecord(
                race_id=race_id,
                title=data.get("title"),
                office=data.get("office"),
                jurisdiction=data.get("jurisdiction"),
                election_date=data.get("election_date"),
                status=status,
                published_at=info.get("pub_utc") if info["published"] else None,
                draft_updated_at=updated_utc if info["draft"] else None,
                candidate_count=len(candidates),
                quality_score=_compute_quality(len(candidates)),
                freshness=_compute_freshness(updated_utc),
                created_at=now,
                updated_at=now,
            )
            self._save_race(record)
            count += 1

        logger.info("RaceManager: hydrated %d new race records from local files", count)
        return count

    def hydrate_from_gcs(self) -> int:
        """Populate race records from GCS. Returns count of new records."""
        from .settings import settings

        gcs_bucket = settings.gcs_bucket
        if not gcs_bucket:
            return 0

        count = 0
        now = _now_iso()

        try:
            from google.cloud import storage as gcs  # type: ignore

            client = gcs.Client()
            bucket = client.bucket(gcs_bucket)
            seen: Dict[str, Dict[str, Any]] = {}

            for prefix, is_published in [("races", True), ("drafts", False)]:
                for blob in bucket.list_blobs(prefix=f"{prefix}/"):
                    if not blob.name.endswith(".json"):
                        continue
                    try:
                        data = json.loads(blob.download_as_text())
                        stem = blob.name[len(f"{prefix}/"):-len(".json")]
                        race_id = data.get("id", stem)
                        if race_id in seen:
                            if not is_published:
                                seen[race_id]["draft"] = True
                                seen[race_id]["data"] = data
                        else:
                            seen[race_id] = {
                                "data": data,
                                "published": is_published,
                                "draft": not is_published,
                                "pub_utc": data.get("updated_utc") if is_published else None,
                            }
                    except Exception:
                        logger.warning("Failed to read GCS blob %s", blob.name)

            for race_id, info in seen.items():
                existing = self.get_race(race_id)
                if existing:
                    # Update metadata without bumping updated_at (hydration only)
                    self._update_metadata_only(race_id, info["data"])
                    continue

                data = info["data"]
                candidates = data.get("candidates", [])
                updated_utc = data.get("updated_utc")
                status = "published" if info["published"] else "draft"

                record = RaceRecord(
                    race_id=race_id,
                    title=data.get("title"),
                    office=data.get("office"),
                    jurisdiction=data.get("jurisdiction"),
                    election_date=data.get("election_date"),
                    status=status,
                    published_at=info.get("pub_utc") if info["published"] else None,
                    draft_updated_at=updated_utc if info.get("draft") else None,
                    candidate_count=len(candidates),
                    quality_score=_compute_quality(len(candidates)),
                    freshness=_compute_freshness(updated_utc),
                    created_at=now,
                    updated_at=now,
                )
                self._save_race(record)
                count += 1

            logger.info("RaceManager: hydrated %d new race records from GCS", count)
        except ImportError:
            logger.warning("google-cloud-storage not installed; skipping GCS hydration")
        except Exception:
            logger.exception("GCS hydration failed")

        return count

    # ── Persistence ───────────────────────────────────────────────────────

    def _save_race(self, record: RaceRecord) -> None:
        # Always update local cache immediately — this ensures reads after writes
        # are consistent even though the Firestore write is asynchronous.
        self._local_races[record.race_id] = record
        if self._db is not None:
            threading.Thread(
                target=self._write_race_firestore,
                args=(record,),
                daemon=True,
            ).start()

    def _write_race_firestore(self, record: RaceRecord) -> None:
        if self._db is None:
            return
        try:
            self._db.collection(_COLLECTION).document(record.race_id).set(
                record.model_dump(mode="json")
            )
        except Exception:
            logger.exception("Firestore write failed for race %s", record.race_id)

    def _write_run_firestore(self, race_id: str, run_id: str, data: dict) -> None:
        if self._db is None:
            return
        # Skip write if the run was deleted before the background thread had a chance to run
        if run_id in self._deleted_run_ids:
            logger.debug("Skipping Firestore write for deleted run %s/%s", race_id, run_id)
            return
        try:
            (
                self._db.collection(_COLLECTION)
                .document(race_id)
                .collection("runs")
                .document(run_id)
                .set(data)
            )
        except Exception:
            logger.exception("Firestore write_run failed for %s/%s", race_id, run_id)


# Global instance
race_manager = RaceManager()
