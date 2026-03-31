"""
Analytics storage backend for request tracking.

Uses Firestore in production (when FIRESTORE_PROJECT env var is set),
falls back to SQLite for local development.
"""

import asyncio
import hashlib
import logging
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _extract_race_id(path: str) -> Optional[str]:
    """Extract race_id from paths like /races/mo-senate-2024."""
    parts = path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "races" and parts[1] and parts[1] != "summaries":
        return parts[1]
    return None


# ---------------------------------------------------------------------------
# Public store class
# ---------------------------------------------------------------------------


class AnalyticsStore:
    """
    Dual-backend analytics store.

    - Firestore AsyncClient when FIRESTORE_PROJECT env var is set (production)
    - SQLite otherwise (local development / testing)
    """

    def __init__(self):
        self._firestore_project = os.getenv("FIRESTORE_PROJECT")
        self._db_path = os.getenv("ANALYTICS_DB_PATH", "data/analytics.db")
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
            # Import deferred to runtime so the package is optional in dev
            import importlib

            from google.cloud import firestore as _firestore  # type: ignore  # noqa: F401

            fs_mod = importlib.import_module("google.cloud.firestore")
            self._client = fs_mod.AsyncClient(project=self._firestore_project)
            logger.info("Analytics: using Firestore project=%s", self._firestore_project)
        except ImportError:
            logger.warning("google-cloud-firestore not installed; falling back to SQLite")
            self._firestore_project = None
            self._init_sqlite()
        except Exception:
            logger.exception("Firestore init failed; falling back to SQLite")
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
            CREATE TABLE IF NOT EXISTS analytics_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp    TEXT NOT NULL,
                path         TEXT NOT NULL,
                race_id      TEXT,
                status_code  INTEGER NOT NULL,
                response_ms  INTEGER NOT NULL,
                ip_hash      TEXT,
                referer      TEXT
            )
        """
        )
        self._sqlite_conn.execute("CREATE INDEX IF NOT EXISTS idx_ts  ON analytics_events(timestamp)")
        self._sqlite_conn.execute("CREATE INDEX IF NOT EXISTS idx_rid ON analytics_events(race_id)")
        self._sqlite_conn.commit()
        logger.info("Analytics: using SQLite %s", self._db_path)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def log_request(
        self,
        path: str,
        status_code: int,
        response_ms: int,
        client_ip: Optional[str],
        referer: Optional[str],
    ) -> None:
        """Record a single request. Designed for fire-and-forget usage."""
        race_id = _extract_race_id(path)
        ip_hash = hashlib.sha256((client_ip or "").encode()).hexdigest()[:16] if client_ip else None
        ts = datetime.now(timezone.utc).isoformat()

        if self._client is not None:
            await self._log_firestore(ts, path, race_id, status_code, response_ms, ip_hash, referer)
        else:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._log_sqlite,
                ts,
                path,
                race_id,
                status_code,
                response_ms,
                ip_hash,
                referer,
            )

    async def _log_firestore(self, ts, path, race_id, status_code, response_ms, ip_hash, referer) -> None:
        try:
            doc = {
                "timestamp": ts,
                "path": path,
                "race_id": race_id,
                "status_code": status_code,
                "response_ms": response_ms,
                "ip_hash": ip_hash,
                "referer": referer,
            }
            await self._client.collection("analytics_events").add(doc)
        except Exception:
            logger.debug("Firestore log_request failed", exc_info=True)

    def _log_sqlite(self, ts, path, race_id, status_code, response_ms, ip_hash, referer) -> None:
        assert self._sqlite_conn is not None
        try:
            self._sqlite_conn.execute(
                "INSERT INTO analytics_events "
                "(timestamp, path, race_id, status_code, response_ms, ip_hash, referer) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, path, race_id, status_code, response_ms, ip_hash, referer),
            )
            self._sqlite_conn.commit()
            # Trim to last 10 000 rows to bound disk usage in dev
            self._sqlite_conn.execute(
                "DELETE FROM analytics_events WHERE id NOT IN "
                "(SELECT id FROM analytics_events ORDER BY id DESC LIMIT 10000)"
            )
            self._sqlite_conn.commit()
        except Exception:
            logger.debug("SQLite log_request failed", exc_info=True)

    # ------------------------------------------------------------------
    # Read — overview
    # ------------------------------------------------------------------

    async def get_overview(self, hours: int = 24) -> Dict[str, Any]:
        """Return aggregate stats for the last *hours* hours."""
        if self._client is not None:
            return await self._overview_firestore(hours)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._overview_sqlite, hours)

    async def _overview_firestore(self, hours: int) -> Dict[str, Any]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        try:
            query = self._client.collection("analytics_events").where("timestamp", ">=", cutoff)
            docs = [doc.to_dict() async for doc in query.stream()]
            return _compute_overview(docs, hours)
        except Exception:
            logger.exception("Firestore overview query failed")
            return _empty_overview(hours)

    def _overview_sqlite(self, hours: int) -> Dict[str, Any]:
        assert self._sqlite_conn is not None
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = self._sqlite_conn.execute(
            "SELECT timestamp, status_code, response_ms, ip_hash " "FROM analytics_events WHERE timestamp >= ?",
            (cutoff,),
        ).fetchall()
        docs = [{"timestamp": r[0], "status_code": r[1], "response_ms": r[2], "ip_hash": r[3]} for r in rows]
        return _compute_overview(docs, hours)

    # ------------------------------------------------------------------
    # Read — per-race stats
    # ------------------------------------------------------------------

    async def get_race_stats(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Return per-race request counts for the last *hours* hours."""
        if self._client is not None:
            return await self._race_stats_firestore(hours)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._race_stats_sqlite, hours)

    async def _race_stats_firestore(self, hours: int) -> List[Dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        try:
            query = self._client.collection("analytics_events").where("timestamp", ">=", cutoff)
            docs = [doc.to_dict() async for doc in query.stream()]
            return _compute_race_stats([d for d in docs if d.get("race_id")])
        except Exception:
            logger.exception("Firestore race stats query failed")
            return []

    def _race_stats_sqlite(self, hours: int) -> List[Dict[str, Any]]:
        assert self._sqlite_conn is not None
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = self._sqlite_conn.execute(
            "SELECT race_id, COUNT(*) as cnt, MAX(timestamp) as last_seen "
            "FROM analytics_events WHERE timestamp >= ? AND race_id IS NOT NULL "
            "GROUP BY race_id ORDER BY cnt DESC",
            (cutoff,),
        ).fetchall()
        return [{"race_id": r[0], "requests_24h": r[1], "last_accessed": r[2]} for r in rows]

    # ------------------------------------------------------------------
    # Read — timeseries
    # ------------------------------------------------------------------

    async def get_timeseries(self, hours: int = 24, bucket_minutes: int = 60) -> List[Dict[str, Any]]:
        """Return bucketed request counts for charting."""
        if self._client is not None:
            return await self._timeseries_firestore(hours, bucket_minutes)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._timeseries_sqlite, hours, bucket_minutes)

    async def _timeseries_firestore(self, hours: int, bucket_minutes: int) -> List[Dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        try:
            query = self._client.collection("analytics_events").where("timestamp", ">=", cutoff)
            docs = [doc.to_dict() async for doc in query.stream()]
            return _compute_timeseries(docs, hours, bucket_minutes)
        except Exception:
            logger.exception("Firestore timeseries query failed")
            return []

    def _timeseries_sqlite(self, hours: int, bucket_minutes: int) -> List[Dict[str, Any]]:
        assert self._sqlite_conn is not None
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = self._sqlite_conn.execute("SELECT timestamp FROM analytics_events WHERE timestamp >= ?", (cutoff,)).fetchall()
        return _compute_timeseries([{"timestamp": r[0]} for r in rows], hours, bucket_minutes)


# ---------------------------------------------------------------------------
# Pure computation helpers
# ---------------------------------------------------------------------------


def _compute_overview(docs: List[Dict[str, Any]], hours: int) -> Dict[str, Any]:
    if not docs:
        return _empty_overview(hours)
    total = len(docs)
    errors = sum(1 for d in docs if (d.get("status_code") or 200) >= 400)
    latencies = [d.get("response_ms") or 0 for d in docs]
    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
    unique_visitors = len({d.get("ip_hash") for d in docs if d.get("ip_hash")})
    error_rate = round(errors / total * 100, 1) if total > 0 else 0.0
    timeseries = _compute_timeseries(docs, hours, 60)
    return {
        "total_requests": total,
        "unique_visitors": unique_visitors,
        "avg_latency_ms": avg_latency,
        "error_rate": error_rate,
        "error_count": errors,
        "timeseries": timeseries,
        "hours": hours,
    }


def _empty_overview(hours: int) -> Dict[str, Any]:
    return {
        "total_requests": 0,
        "unique_visitors": 0,
        "avg_latency_ms": 0,
        "error_rate": 0.0,
        "error_count": 0,
        "timeseries": [],
        "hours": hours,
    }


def _compute_race_stats(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = defaultdict(int)
    last_seen: Dict[str, str] = {}
    for d in docs:
        rid = d.get("race_id")
        if rid:
            counts[rid] += 1
            ts = d.get("timestamp", "")
            if ts > last_seen.get(rid, ""):
                last_seen[rid] = ts
    return [
        {"race_id": rid, "requests_24h": counts[rid], "last_accessed": last_seen.get(rid)}
        for rid in sorted(counts, key=lambda x: -counts[x])
    ]


def _compute_timeseries(docs: List[Dict[str, Any]], hours: int, bucket_minutes: int) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    bucket_count = max(1, (hours * 60) // bucket_minutes)
    buckets: Dict[int, int] = defaultdict(int)

    for d in docs:
        ts_str = d.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            minutes_ago = int((now - ts).total_seconds() / 60)
            bucket_idx = minutes_ago // bucket_minutes
            if 0 <= bucket_idx < bucket_count:
                buckets[bucket_count - 1 - bucket_idx] += 1
        except (ValueError, TypeError):
            continue

    result = []
    for i in range(bucket_count):
        bucket_time = now - timedelta(minutes=(bucket_count - 1 - i) * bucket_minutes)
        result.append({"time": bucket_time.strftime("%H:%M"), "requests": buckets[i]})
    return result
