"""
Domain-aware alert evaluation engine for the pipeline-client admin dashboard.

Evaluates four categories of alerts:
- Data freshness: how recently each race was updated
- Pipeline failures: consecutive failure counts per race
- Content quality: issue coverage and confidence scores
- Analytics health: API error rate (from proxied analytics data)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
ACKNOWLEDGED_FILE = Path(__file__).parent.parent / "acknowledged_alerts.json"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Alert:
    id: str
    severity: str  # "info" | "warning" | "critical"
    category: str  # "freshness" | "failures" | "quality" | "analytics"
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "details": self.details,
            "created_at": self.created_at,
            "acknowledged": self.acknowledged,
        }


# ---------------------------------------------------------------------------
# Acknowledgement persistence
# ---------------------------------------------------------------------------


def _load_acknowledged() -> set:
    try:
        if ACKNOWLEDGED_FILE.exists():
            data = json.loads(ACKNOWLEDGED_FILE.read_text(encoding="utf-8"))
            return set(data.get("acknowledged_ids", []))
    except Exception:
        logger.debug("Could not load acknowledged alerts file", exc_info=True)
    return set()


def _save_acknowledged(ids: set) -> None:
    try:
        ACKNOWLEDGED_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACKNOWLEDGED_FILE.write_text(json.dumps({"acknowledged_ids": sorted(ids)}, indent=2), encoding="utf-8")
    except Exception:
        logger.warning("Could not save acknowledged alerts file", exc_info=True)


def acknowledge_alert(alert_id: str) -> bool:
    """Mark an alert as acknowledged. Returns True if successfully saved."""
    ids = _load_acknowledged()
    ids.add(alert_id)
    _save_acknowledged(ids)
    return True


# ---------------------------------------------------------------------------
# Alert evaluation
# ---------------------------------------------------------------------------


def _load_races(races_dir: Path) -> List[Dict[str, Any]]:
    """Load all published race JSON files from the local data directory."""
    races = []
    if not races_dir.exists():
        return races
    for path in races_dir.glob("*.json"):
        if path.suffix == ".backup" or ".backup." in path.name:
            continue
        try:
            races.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            logger.debug("Could not load race file %s", path, exc_info=True)
    return races


def _parse_utc(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def evaluate_freshness(races: List[Dict[str, Any]]) -> List[Alert]:
    """Emit alerts for races not updated recently."""
    now = datetime.now(timezone.utc)
    alerts: List[Alert] = []

    for race in races:
        race_id = race.get("id", "unknown")
        updated = _parse_utc(race.get("updated_utc"))
        if updated is None:
            alerts.append(
                Alert(
                    id=f"freshness-no-date-{race_id}",
                    severity="warning",
                    category="freshness",
                    message=f"Race {race_id} has no update timestamp",
                    details={"race_id": race_id},
                )
            )
            continue

        age_days = (now - updated).days
        if age_days > 30:
            alerts.append(
                Alert(
                    id=f"freshness-critical-{race_id}",
                    severity="critical",
                    category="freshness",
                    message=f"Race {race_id} has not been updated in {age_days} days",
                    details={"race_id": race_id, "age_days": age_days, "updated_utc": race.get("updated_utc")},
                )
            )
        elif age_days > 14:
            alerts.append(
                Alert(
                    id=f"freshness-warning-{race_id}",
                    severity="warning",
                    category="freshness",
                    message=f"Race {race_id} has not been updated in {age_days} days",
                    details={"race_id": race_id, "age_days": age_days, "updated_utc": race.get("updated_utc")},
                )
            )

    return alerts


def evaluate_pipeline_failures(run_manager) -> List[Alert]:
    """Emit alerts for races with consecutive pipeline failures."""
    alerts: List[Alert] = []
    try:
        runs = run_manager.list_recent_runs(limit=100)
    except Exception:
        logger.debug("Could not list recent runs for failure check", exc_info=True)
        return alerts

    # Count consecutive failures per race (most-recent-first order)
    consecutive: Dict[str, int] = {}
    seen: set = set()

    for run in runs:
        race_id = (run.payload or {}).get("race_id", "unknown")
        if race_id in seen:
            continue
        seen.add(race_id)
        status = str(run.status.value if hasattr(run.status, "value") else run.status)
        if status == "failed":
            consecutive[race_id] = consecutive.get(race_id, 0) + 1
        elif status == "completed":
            consecutive[race_id] = 0

    for race_id, count in consecutive.items():
        if count >= 5:
            alerts.append(
                Alert(
                    id=f"failures-critical-{race_id}",
                    severity="critical",
                    category="failures",
                    message=f"Race {race_id} has {count} consecutive pipeline failures",
                    details={"race_id": race_id, "consecutive_failures": count},
                )
            )
        elif count >= 2:
            alerts.append(
                Alert(
                    id=f"failures-warning-{race_id}",
                    severity="warning",
                    category="failures",
                    message=f"Race {race_id} has {count} consecutive pipeline failures",
                    details={"race_id": race_id, "consecutive_failures": count},
                )
            )

    return alerts


def evaluate_quality(races: List[Dict[str, Any]]) -> List[Alert]:
    """Emit alerts for races with poor data quality."""
    alerts: List[Alert] = []
    TOTAL_ISSUES = 12

    for race in races:
        race_id = race.get("id", "unknown")
        candidates = race.get("candidates", [])

        for candidate in candidates:
            name = candidate.get("name", "?")
            issues = candidate.get("issues", {})
            issue_count = len([v for v in issues.values() if v and v.get("stance")])

            if issue_count < 6:
                alerts.append(
                    Alert(
                        id=f"quality-critical-{race_id}-{name}",
                        severity="critical",
                        category="quality",
                        message=f"{name} ({race_id}) only has {issue_count}/{TOTAL_ISSUES} issue stances",
                        details={"race_id": race_id, "candidate": name, "issues_covered": issue_count},
                    )
                )
            elif issue_count < 8:
                alerts.append(
                    Alert(
                        id=f"quality-warning-{race_id}-{name}",
                        severity="warning",
                        category="quality",
                        message=f"{name} ({race_id}) only has {issue_count}/{TOTAL_ISSUES} issue stances",
                        details={"race_id": race_id, "candidate": name, "issues_covered": issue_count},
                    )
                )

            # Check confidence — warn if more than half of stances are low/unknown
            conf_map = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
            stance_vals = [v for v in issues.values() if v and v.get("stance")]
            if stance_vals:
                avg_conf = sum(conf_map.get(v.get("confidence", "unknown"), 0) for v in stance_vals) / len(stance_vals)
                if avg_conf < 1.0:
                    alerts.append(
                        Alert(
                            id=f"quality-confidence-{race_id}-{name}",
                            severity="warning",
                            category="quality",
                            message=f"{name} ({race_id}) has low average confidence in stances",
                            details={"race_id": race_id, "candidate": name, "avg_confidence_score": round(avg_conf, 2)},
                        )
                    )

    return alerts


def evaluate_analytics_health(overview: Optional[Dict[str, Any]]) -> List[Alert]:
    """Emit alerts based on API error rate from analytics overview."""
    if overview is None:
        return []
    alerts: List[Alert] = []
    error_rate = overview.get("error_rate", 0.0)
    total = overview.get("total_requests", 0)

    # Only alert if there's meaningful traffic
    if total < 10:
        return alerts

    if error_rate > 15:
        alerts.append(
            Alert(
                id="analytics-error-rate-critical",
                severity="critical",
                category="analytics",
                message=f"races-api error rate is {error_rate}% (>{15}% threshold)",
                details={"error_rate": error_rate, "total_requests": total},
            )
        )
    elif error_rate > 5:
        alerts.append(
            Alert(
                id="analytics-error-rate-warning",
                severity="warning",
                category="analytics",
                message=f"races-api error rate is {error_rate}% (>{5}% threshold)",
                details={"error_rate": error_rate, "total_requests": total},
            )
        )

    return alerts


def evaluate_all(run_manager, overview: Optional[Dict[str, Any]] = None) -> List[Alert]:
    """Run all alert rules and return active (non-acknowledged) alerts."""
    races_dir = ROOT / "data" / "published"
    races = _load_races(races_dir)
    acknowledged = _load_acknowledged()

    all_alerts: List[Alert] = []
    all_alerts.extend(evaluate_freshness(races))
    all_alerts.extend(evaluate_pipeline_failures(run_manager))
    all_alerts.extend(evaluate_quality(races))
    all_alerts.extend(evaluate_analytics_health(overview))

    # Apply acknowledgements
    for alert in all_alerts:
        if alert.id in acknowledged:
            alert.acknowledged = True

    # Sort: critical first, then warning, then acknowledged
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    all_alerts.sort(key=lambda a: (a.acknowledged, severity_order.get(a.severity, 9), a.id))

    return all_alerts
