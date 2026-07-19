import sqlite3
from datetime import datetime, timezone

import analytics_store


def test_sqlite_trim_is_deterministic_and_bounded(monkeypatch, tmp_path):
    monkeypatch.delenv("FIRESTORE_PROJECT", raising=False)
    monkeypatch.setenv("ANALYTICS_DB_PATH", str(tmp_path / "analytics.db"))
    monkeypatch.setattr(analytics_store, "_SQLITE_EVENT_LIMIT", 10)
    monkeypatch.setattr(analytics_store, "_SQLITE_TRIM_INTERVAL", 5)
    store = analytics_store.AnalyticsStore()
    timestamp = datetime.now(timezone.utc).isoformat()

    for index in range(15):
        store._log_sqlite(timestamp, f"/races/test-{index}", None, 200, 10, None, None)

    with sqlite3.connect(store._db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM analytics_events").fetchone()[0]

    assert count == 10
