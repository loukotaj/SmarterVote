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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from shared.config import FIRESTORE_METRICS_COLLECTION, local_paths

logger = logging.getLogger("pipeline")


class PipelineMetricsStore:
    """
    Dual-backend pipeline metrics store.

    - Firestore AsyncClient when FIRESTORE_PROJECT env var is set (production)
    - SQLite otherwise (local development / testing)

    Schema per record::

        run_id          str   — unique run ID (UUID)
        race_id         str   — race identifier (e.g. ``mo-senate-2024``)
        timestamp       str   — ISO-8601 UTC
        status          str   — ``"completed"`` | ``"failed"``
        model           str   — primary LLM model used
        prompt_tokens   int
        completion_tokens int
        total_tokens    int
        cost_usd        float — exact provider-reported spend when available
        cost_source     str   — "provider" or "estimated"
        estimated_usd   float — catalog estimate including review models
        model_breakdown dict  — per-model token breakdown
        duration_s      float — wall-clock run time in seconds
        candidate_count int   — number of candidates in the output (0 for failed runs)
        cheap_mode      bool  — whether the run used cheap/fast model variants
        serper_calls      int
    """

    _COLLECTION = FIRESTORE_METRICS_COLLECTION

    def __init__(self) -> None:
        explicit_db_path = os.getenv("PIPELINE_METRICS_DB_PATH")
        self._firestore_project = os.getenv("FIRESTORE_PROJECT")
        if not self._firestore_project and not explicit_db_path:
            self._firestore_project = os.getenv("GOOGLE_CLOUD_PROJECT")
        self._db_path = explicit_db_path or str(local_paths.metrics_db_path)
        self._client = None

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
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
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
                    llm_cost_usd       REAL,
                    search_cost_usd    REAL NOT NULL DEFAULT 0,
                    cost_usd          REAL,
                    cost_source       TEXT NOT NULL DEFAULT 'estimated',
                    model_breakdown   TEXT NOT NULL DEFAULT '{}',
                    phase_breakdown   TEXT NOT NULL DEFAULT '{}',
                    duration_s        REAL NOT NULL DEFAULT 0,
                    candidate_count   INTEGER NOT NULL DEFAULT 0,
                    cheap_mode        INTEGER NOT NULL DEFAULT 0,
                    serper_calls      INTEGER NOT NULL DEFAULT 0,
                    searlo_calls      INTEGER NOT NULL DEFAULT 0,
                    search_calls      INTEGER NOT NULL DEFAULT 0,
                    search_budget_blocked INTEGER NOT NULL DEFAULT 0,
                    token_budget_nudges INTEGER NOT NULL DEFAULT 0,
                    segment_duration_s REAL NOT NULL DEFAULT 0
                    ,page_fetches INTEGER NOT NULL DEFAULT 0
                    ,fetched_chars INTEGER NOT NULL DEFAULT 0
                    ,page_budget_blocked INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pm_ts  ON pipeline_metrics(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pm_rid ON pipeline_metrics(race_id)")
            # Migrate existing DBs that were created before these columns existed
            for col_def in [
                "candidate_count INTEGER NOT NULL DEFAULT 0",
                "cheap_mode INTEGER NOT NULL DEFAULT 0",
                "cost_usd REAL",
                "llm_cost_usd REAL",
                "search_cost_usd REAL NOT NULL DEFAULT 0",
                "cost_source TEXT NOT NULL DEFAULT 'estimated'",
                "serper_calls INTEGER NOT NULL DEFAULT 0",
                "searlo_calls INTEGER NOT NULL DEFAULT 0",
                "search_calls INTEGER NOT NULL DEFAULT 0",
                "search_budget_blocked INTEGER NOT NULL DEFAULT 0",
                "token_budget_nudges INTEGER NOT NULL DEFAULT 0",
                "segment_duration_s REAL NOT NULL DEFAULT 0",
                "phase_breakdown TEXT NOT NULL DEFAULT '{}'",
                "page_fetches INTEGER NOT NULL DEFAULT 0",
                "fetched_chars INTEGER NOT NULL DEFAULT 0",
                "page_budget_blocked INTEGER NOT NULL DEFAULT 0",
            ]:
                try:
                    conn.execute(f"ALTER TABLE pipeline_metrics ADD COLUMN {col_def}")
                except sqlite3.OperationalError:
                    pass  # column already exists
            conn.commit()
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
        candidate_count: int = 0,
        cheap_mode: bool = True,
        serper_calls: int = 0,
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
            "llm_cost_usd": agent_metrics.get("llm_cost_usd"),
            "search_cost_usd": agent_metrics.get("search_cost_usd", 0.0),
            "cost_usd": agent_metrics.get("cost_usd"),
            "cost_source": agent_metrics.get("cost_source", "estimated"),
            "model_breakdown": agent_metrics.get("model_breakdown", {}),
            "phase_breakdown": agent_metrics.get("phase_breakdown", {}),
            "page_fetches": agent_metrics.get("page_fetches", 0),
            "fetched_chars": agent_metrics.get("fetched_chars", 0),
            "page_budget_blocked": agent_metrics.get("page_budget_blocked", 0),
            "duration_s": agent_metrics.get("duration_s", 0.0),
            "candidate_count": candidate_count,
            "cheap_mode": cheap_mode,
            "serper_calls": serper_calls,
            "searlo_calls": agent_metrics.get("searlo_calls", 0),
            "search_calls": agent_metrics.get("search_calls", serper_calls),
            "search_budget_blocked": agent_metrics.get("search_budget_blocked", 0),
            "token_budget_nudges": agent_metrics.get("token_budget_nudges", 0),
            "segment_duration_s": agent_metrics.get("segment_duration_s", 0.0),
        }

        if self._client is not None:
            await self._write_firestore(run_id, record)
        else:
            loop = asyncio.get_running_loop()
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
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pipeline_metrics
                        (run_id, race_id, timestamp, status, model,
                         prompt_tokens, completion_tokens, total_tokens,
                         estimated_usd, llm_cost_usd, search_cost_usd,
                         cost_usd, cost_source, model_breakdown, phase_breakdown, duration_s,
                         candidate_count, cheap_mode, serper_calls, searlo_calls,
                         search_calls, search_budget_blocked, token_budget_nudges,
                         segment_duration_s, page_fetches, fetched_chars, page_budget_blocked)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                        record["llm_cost_usd"],
                        record["search_cost_usd"],
                        record["cost_usd"],
                        record["cost_source"],
                        json.dumps(record["model_breakdown"]),
                        json.dumps(record["phase_breakdown"]),
                        record["duration_s"],
                        record.get("candidate_count", 0),
                        int(record.get("cheap_mode", True)),
                        record.get("serper_calls", 0),
                        record.get("searlo_calls", 0),
                        record.get("search_calls", 0),
                        record.get("search_budget_blocked", 0),
                        record.get("token_budget_nudges", 0),
                        record.get("segment_duration_s", 0.0),
                        record.get("page_fetches", 0),
                        record.get("fetched_chars", 0),
                        record.get("page_budget_blocked", 0),
                    ),
                )
                conn.commit()
        except Exception:
            logger.exception("Failed to write pipeline metrics to SQLite")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent *limit* pipeline run records, newest first."""
        if self._client is not None:
            return await self._read_recent_firestore(limit)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_recent_sqlite, limit)

    async def _read_recent_firestore(self, limit: int) -> List[Dict[str, Any]]:
        try:
            assert self._client is not None
            docs = (
                self._client.collection(self._COLLECTION).order_by("timestamp", direction="DESCENDING").limit(limit).stream()
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
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT run_id, race_id, timestamp, status, model,
                           prompt_tokens, completion_tokens, total_tokens,
                           estimated_usd, llm_cost_usd, search_cost_usd,
                           cost_usd, cost_source, model_breakdown, phase_breakdown, duration_s,
                           candidate_count, cheap_mode, serper_calls, searlo_calls,
                           search_calls, search_budget_blocked, token_budget_nudges,
                           segment_duration_s, page_fetches, fetched_chars, page_budget_blocked
                    FROM pipeline_metrics
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
            rows_list = []
            for row in rows:
                (
                    run_id,
                    race_id,
                    timestamp,
                    status,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    estimated_usd,
                    llm_cost_usd,
                    search_cost_usd,
                    cost_usd,
                    cost_source,
                    model_breakdown_json,
                    phase_breakdown_json,
                    duration_s,
                    candidate_count,
                    cheap_mode_int,
                    serper_calls,
                    searlo_calls,
                    search_calls,
                    search_budget_blocked,
                    token_budget_nudges,
                    segment_duration_s,
                    page_fetches,
                    fetched_chars,
                    page_budget_blocked,
                ) = row
                rows_list.append(
                    {
                        "run_id": run_id,
                        "race_id": race_id,
                        "timestamp": timestamp,
                        "status": status,
                        "model": model,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                        "estimated_usd": estimated_usd,
                        "llm_cost_usd": llm_cost_usd,
                        "search_cost_usd": search_cost_usd,
                        "cost_usd": cost_usd,
                        "cost_source": cost_source,
                        "model_breakdown": json.loads(model_breakdown_json or "{}"),
                        "phase_breakdown": json.loads(phase_breakdown_json or "{}"),
                        "duration_s": duration_s,
                        "candidate_count": candidate_count or 0,
                        "cheap_mode": bool(cheap_mode_int),
                        "serper_calls": serper_calls or 0,
                        "searlo_calls": searlo_calls or 0,
                        "search_calls": search_calls or 0,
                        "search_budget_blocked": search_budget_blocked or 0,
                        "token_budget_nudges": token_budget_nudges or 0,
                        "segment_duration_s": segment_duration_s or 0.0,
                        "page_fetches": page_fetches or 0,
                        "fetched_chars": fetched_chars or 0,
                        "page_budget_blocked": page_budget_blocked or 0,
                    }
                )
            return rows_list
        except Exception:
            logger.exception("Failed to read pipeline metrics from SQLite")
            return []

    async def get_summary(self) -> Dict[str, Any]:
        """Return aggregate stats across all recorded runs."""
        if self._client is not None:
            return await self._summary_firestore()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._summary_sqlite)

    async def _summary_firestore(self) -> Dict[str, Any]:
        try:
            assert self._client is not None
            # The summary needs every cost field, so a separate count aggregation
            # would add a billed read without reducing the document stream.
            docs = self._client.collection(self._COLLECTION).stream()
            records = [doc.to_dict() async for doc in docs]
            return _compute_metrics_summary(records)
        except Exception:
            logger.exception("Failed to compute Firestore pipeline metrics summary")
            return _empty_summary()

    def _summary_sqlite(self) -> Dict[str, Any]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                total_row = conn.execute("SELECT COUNT(*) FROM pipeline_metrics").fetchone()
                total_runs = total_row[0] if total_row else 0

                cost_row = conn.execute(
                    "SELECT COALESCE(SUM(COALESCE(cost_usd, estimated_usd)),0) FROM pipeline_metrics"
                ).fetchone()
                total_usd = cost_row[0] if cost_row else 0.0

                cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
                recent_row = conn.execute(
                    "SELECT COALESCE(SUM(COALESCE(cost_usd, estimated_usd)),0) " "FROM pipeline_metrics WHERE timestamp >= ?",
                    (cutoff,),
                ).fetchone()
                recent_usd = recent_row[0] if recent_row else 0.0

                ok_row = conn.execute("SELECT COUNT(*) FROM pipeline_metrics WHERE status = 'completed'").fetchone()
                completed_runs = ok_row[0] if ok_row else 0

                cheap_row = conn.execute(
                    "SELECT COUNT(*), COALESCE(SUM(COALESCE(cost_usd, estimated_usd)),0) "
                    "FROM pipeline_metrics WHERE cheap_mode = 1"
                ).fetchone()
                cheap_runs, cheap_usd = cheap_row if cheap_row else (0, 0.0)

                full_row = conn.execute(
                    "SELECT COUNT(*), COALESCE(SUM(COALESCE(cost_usd, estimated_usd)),0) "
                    "FROM pipeline_metrics WHERE cheap_mode = 0"
                ).fetchone()
                full_runs, full_usd = full_row if full_row else (0, 0.0)

                cand_row = conn.execute(
                    "SELECT COALESCE(SUM(candidate_count),0), "
                    "COALESCE(SUM(COALESCE(cost_usd, estimated_usd)),0) "
                    "FROM pipeline_metrics WHERE candidate_count > 0"
                ).fetchone()
                total_candidates, usd_with_candidates = cand_row if cand_row else (0, 0.0)

            return {
                "total_runs": total_runs,
                "total_usd": round(total_usd, 4),
                "avg_usd": round(total_usd / total_runs, 4) if total_runs else 0.0,
                "recent_30d_usd": round(recent_usd, 4),
                "success_rate": round(completed_runs / total_runs, 3) if total_runs else 0.0,
                "cheap_runs": cheap_runs,
                "avg_cheap_usd": round(cheap_usd / cheap_runs, 4) if cheap_runs else 0.0,
                "full_runs": full_runs,
                "avg_full_usd": round(full_usd / full_runs, 4) if full_runs else 0.0,
                "avg_usd_per_candidate": round(usd_with_candidates / total_candidates, 4) if total_candidates else 0.0,
            }
        except Exception:
            logger.exception("Failed to compute SQLite pipeline metrics summary")
            return _empty_summary()


def _empty_summary() -> Dict[str, Any]:
    return {
        "total_runs": 0,
        "total_usd": 0.0,
        "avg_usd": 0.0,
        "recent_30d_usd": 0.0,
        "success_rate": 0.0,
        "cheap_runs": 0,
        "avg_cheap_usd": 0.0,
        "full_runs": 0,
        "avg_full_usd": 0.0,
        "avg_usd_per_candidate": 0.0,
    }


def _compute_metrics_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_runs = len(records)
    if total_runs == 0:
        return _empty_summary()

    completed_runs = 0
    total_usd = 0.0
    recent_usd = 0.0
    cheap_runs = 0
    cheap_usd = 0.0
    full_runs = 0
    full_usd = 0.0
    total_candidates = 0
    total_usd_with_candidates = 0.0

    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    for data in records:
        usd = data.get("cost_usd")
        if usd is None:
            usd = data.get("estimated_usd", 0.0)
        total_usd += usd
        if (data.get("status") or "completed") == "completed":
            completed_runs += 1
        if data.get("timestamp", "") >= cutoff:
            recent_usd += usd
        if data.get("cheap_mode", True):
            cheap_runs += 1
            cheap_usd += usd
        else:
            full_runs += 1
            full_usd += usd
        cands = data.get("candidate_count", 0) or 0
        if cands > 0:
            total_candidates += cands
            total_usd_with_candidates += usd

    return {
        "total_runs": total_runs,
        "total_usd": round(total_usd, 4),
        "avg_usd": round(total_usd / total_runs, 4) if total_runs else 0.0,
        "recent_30d_usd": round(recent_usd, 4),
        "success_rate": round(completed_runs / total_runs, 3) if total_runs else 0.0,
        "cheap_runs": cheap_runs,
        "avg_cheap_usd": round(cheap_usd / cheap_runs, 4) if cheap_runs else 0.0,
        "full_runs": full_runs,
        "avg_full_usd": round(full_usd / full_runs, 4) if full_runs else 0.0,
        "avg_usd_per_candidate": round(total_usd_with_candidates / total_candidates, 4) if total_candidates else 0.0,
    }


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
