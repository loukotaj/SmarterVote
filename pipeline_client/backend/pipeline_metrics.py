"""Pipeline run metrics store.

Persists per-run token usage and cost data for the AI research pipeline.
Uses Firestore in production (when ``FIRESTORE_PROJECT`` env var is set),
falls back to a local SQLite DB for development.
"""

import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PipelineMetricsStore:
    """
    Dual-backend pipeline metrics store.

    - Firestore AsyncClient when FIRESTORE_PROJECT env var is set (production)
    - SQLite otherwise (local development / testing)

    Schema per record::

        run_id          str   — unique run ID (UUID)
        race_id         str   — race identifier (e.g. ``mo-senate-2024``)
        timestamp       str   — ISO-8601 UTC
        status          str   — ``"completed"`` | ``"failed"`` | ``"partial"``
        model           str   — primary LLM model used
        prompt_tokens   int
        completion_tokens int
        total_tokens    int
        estimated_usd   float — total estimated spend including review models
        model_breakdown dict  — per-model token breakdown
        duration_s      float — wall-clock run time in seconds
    """

    _COLLECTION = "pipeline_metrics"

    def __init__(self) -> None:
        self._firestore_project = os.getenv("FIRESTORE_PROJECT")
        self._db_path = os.getenv("PIPELINE_METRICS_DB_PATH", "data/pipeline_metrics.db")
        self._client = None
        self._sqlite_conn: Optional[sqlite3.Connection] = None

        if self._firestore_project:
            self._init_firestore()
        else:
            self._init_sqlite()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_firestore(self) -> None:
        try:
            import importlib

            import google.cloud.firestore  # noqa: F401

            fs_mod = importlib.import_module("google.cloud.firestore")
            self._client = fs_mod.AsyncClient(project=self._firestore_project)
            logger.info("PipelineMetrics: using Firestore project=%s", self._firestore_project)
        except ImportError:
            logger.warning("google-cloud-firestore not installed; falling back to SQLite for pipeline metrics")
            self._firestore_project = None
            self._init_sqlite()
        except Exception:
            logger.exception("Firestore init failed for pipeline metrics; falling back to SQLite")
            self._firestore_project = None
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._sqlite_conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._sqlite_conn.execute("PRAGMA journal_mode=WAL")
        self._sqlite_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_metrics (
                run_id            TEXT PRIMARY KEY,
                race_id           TEXT NOT NULL,
                timestamp         TEXT NOT NULL,
                status            TEXT NOT NULL,
                model             TEXT NOT NULL DEFAULT '',
                prompt_tokens     INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens      INTEGER NOT NULL DEFAULT 0,
                estimated_usd     REAL NOT NULL DEFAULT 0,
                model_breakdown   TEXT NOT NULL DEFAULT '{}',
                duration_s        REAL NOT NULL DEFAULT 0
            )
            """
        )
        self._sqlite_conn.execute("CREATE INDEX IF NOT EXISTS idx_pm_ts  ON pipeline_metrics(timestamp)")
        self._sqlite_conn.execute("CREATE INDEX IF NOT EXISTS idx_pm_rid ON pipeline_metrics(race_id)")
        self._sqlite_conn.commit()
        logger.info("PipelineMetrics: using SQLite %s", self._db_path)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def record_run(
        self,
        run_id: str,
        race_id: str,
        agent_metrics: Optional[Dict[str, Any]],
        status: str = "completed",
    ) -> None:
        """Persist a pipeline run record. Safe to call fire-and-forget."""
        if not agent_metrics:
            agent_metrics = {}

        ts = datetime.now(timezone.utc).isoformat()
        record: Dict[str, Any] = {
            "run_id": run_id,
            "race_id": race_id,
            "timestamp": ts,
            "status": status,
            "model": agent_metrics.get("model", ""),
            "prompt_tokens": agent_metrics.get("prompt_tokens", 0),
            "completion_tokens": agent_metrics.get("completion_tokens", 0),
            "total_tokens": agent_metrics.get("total_tokens", 0),
            "estimated_usd": agent_metrics.get("estimated_usd", 0.0),
            "model_breakdown": agent_metrics.get("model_breakdown", {}),
            "duration_s": agent_metrics.get("duration_s", 0.0),
        }

        if self._client is not None:
            await self._write_firestore(run_id, record)
        else:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_sqlite, record)

    async def _write_firestore(self, run_id: str, record: Dict[str, Any]) -> None:
        try:
            assert self._client is not None
            doc = self._client.collection(self._COLLECTION).document(run_id)
            await doc.set(record)
        except Exception:
            logger.exception("Failed to write pipeline metrics to Firestore for run %s", run_id)

    def _write_sqlite(self, record: Dict[str, Any]) -> None:
        try:
            assert self._sqlite_conn is not None
            self._sqlite_conn.execute(
                """
                INSERT OR REPLACE INTO pipeline_metrics
                    (run_id, race_id, timestamp, status, model,
                     prompt_tokens, completion_tokens, total_tokens,
                     estimated_usd, model_breakdown, duration_s)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record["run_id"],
                    record["race_id"],
                    record["timestamp"],
                    record["status"],
                    record["model"],
                    record["prompt_tokens"],
                    record["completion_tokens"],
                    record["total_tokens"],
                    record["estimated_usd"],
                    json.dumps(record["model_breakdown"]),
                    record["duration_s"],
                ),
            )
            self._sqlite_conn.commit()
        except Exception:
            logger.exception("Failed to write pipeline metrics to SQLite")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent *limit* pipeline run records, newest first."""
        if self._client is not None:
            return await self._read_recent_firestore(limit)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._read_recent_sqlite, limit)

    async def _read_recent_firestore(self, limit: int) -> List[Dict[str, Any]]:
        try:
            assert self._client is not None
            docs = (
                self._client.collection(self._COLLECTION)
                .order_by("timestamp", direction="DESCENDING")
                .limit(limit)
                .stream()
            )
            results = []
            async for doc in docs:
                results.append(doc.to_dict())
            return results
        except Exception:
            logger.exception("Failed to read pipeline metrics from Firestore")
            return []

    def _read_recent_sqlite(self, limit: int) -> List[Dict[str, Any]]:
        try:
            assert self._sqlite_conn is not None
            cursor = self._sqlite_conn.execute(
                """
                SELECT run_id, race_id, timestamp, status, model,
                       prompt_tokens, completion_tokens, total_tokens,
                       estimated_usd, model_breakdown, duration_s
                FROM pipeline_metrics
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = []
            for row in cursor.fetchall():
                (
                    run_id, race_id, timestamp, status, model,
                    prompt_tokens, completion_tokens, total_tokens,
                    estimated_usd, model_breakdown_json, duration_s,
                ) = row
                rows.append({
                    "run_id": run_id,
                    "race_id": race_id,
                    "timestamp": timestamp,
                    "status": status,
                    "model": model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "estimated_usd": estimated_usd,
                    "model_breakdown": json.loads(model_breakdown_json or "{}"),
                    "duration_s": duration_s,
                })
            return rows
        except Exception:
            logger.exception("Failed to read pipeline metrics from SQLite")
            return []

    async def get_summary(self) -> Dict[str, Any]:
        """Return aggregate stats across all recorded runs."""
        if self._client is not None:
            return await self._summary_firestore()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._summary_sqlite)

    async def _summary_firestore(self) -> Dict[str, Any]:
        try:
            assert self._client is not None
            docs = self._client.collection(self._COLLECTION).stream()
            total_runs = 0
            total_usd = 0.0
            recent_usd = 0.0
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            async for doc in docs:
                data = doc.to_dict()
                total_runs += 1
                usd = data.get("estimated_usd", 0.0)
                total_usd += usd
                if data.get("timestamp", "") >= cutoff:
                    recent_usd += usd
            return {
                "total_runs": total_runs,
                "total_usd": round(total_usd, 4),
                "avg_usd": round(total_usd / total_runs, 4) if total_runs else 0.0,
                "recent_30d_usd": round(recent_usd, 4),
            }
        except Exception:
            logger.exception("Failed to compute Firestore pipeline metrics summary")
            return {"total_runs": 0, "total_usd": 0.0, "avg_usd": 0.0, "recent_30d_usd": 0.0}

    def _summary_sqlite(self) -> Dict[str, Any]:
        try:
            assert self._sqlite_conn is not None
            row = self._sqlite_conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(estimated_usd),0) FROM pipeline_metrics"
            ).fetchone()
            total_runs, total_usd = row
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            recent_row = self._sqlite_conn.execute(
                "SELECT COALESCE(SUM(estimated_usd),0) FROM pipeline_metrics WHERE timestamp >= ?",
                (cutoff,),
            ).fetchone()
            recent_usd = recent_row[0]
            return {
                "total_runs": total_runs,
                "total_usd": round(total_usd, 4),
                "avg_usd": round(total_usd / total_runs, 4) if total_runs else 0.0,
                "recent_30d_usd": round(recent_usd, 4),
            }
        except Exception:
            logger.exception("Failed to compute SQLite pipeline metrics summary")
            return {"total_runs": 0, "total_usd": 0.0, "avg_usd": 0.0, "recent_30d_usd": 0.0}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store: Optional[PipelineMetricsStore] = None


def get_pipeline_metrics_store() -> PipelineMetricsStore:
    """Return (and lazily create) the process-level metrics store singleton."""
    global _store
    if _store is None:
        _store = PipelineMetricsStore()
    return _store
