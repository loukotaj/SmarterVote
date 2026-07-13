"""Query the Cloud Billing BigQuery export for GCP spend.

The billing export is enabled once in the Cloud Console (billing-account
scoped) and streams a table named ``gcp_billing_export_*`` into the
``billing_export`` dataset (created by infra/billing-export.tf). This module
discovers that table and aggregates net cost (gross cost plus credits) by
service over a recent window.

Everything degrades gracefully: if BigQuery is unavailable, the dataset/table
does not exist yet, or the export has not produced data, callers receive
``{"configured": False, "reason": ...}`` instead of an error.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger("races_api")

_DATASET = os.getenv("BILLING_EXPORT_DATASET", "billing_export")
_TABLE_PREFIX = "gcp_billing_export"


def _project_id() -> str:
    return os.getenv("FIRESTORE_PROJECT") or os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or ""


def get_gcp_costs(days: int = 30) -> Dict[str, Any]:
    """Return GCP cost aggregated by service over the last *days* days."""
    days = max(1, min(days, 365))
    project = _project_id()
    if not project:
        return {"configured": False, "reason": "No GCP project configured (set PROJECT_ID/FIRESTORE_PROJECT)."}

    try:
        from google.cloud import bigquery
    except ImportError:
        return {"configured": False, "reason": "google-cloud-bigquery not installed."}

    try:
        client = bigquery.Client(project=project)
    except Exception as exc:  # noqa: BLE001 - surface as unconfigured, never 500
        logger.warning("BigQuery client init failed: %s", exc)
        return {"configured": False, "reason": f"BigQuery unavailable: {exc}"}

    dataset_ref = f"{project}.{_DATASET}"

    # Discover the export table (its suffix is the billing-account id).
    try:
        tables = list(client.list_tables(dataset_ref))
    except Exception as exc:  # noqa: BLE001
        return {
            "configured": False,
            "reason": (
                f"Billing export dataset '{_DATASET}' not found or unreadable. "
                "Run terraform apply, then enable the export in the Cloud Console."
            ),
            "detail": str(exc),
        }

    export_tables = [t for t in tables if t.table_id.startswith(_TABLE_PREFIX)]
    if not export_tables:
        return {
            "configured": False,
            "reason": (
                "Billing export dataset exists but no export table yet. "
                "Enable 'Detailed usage cost' export in the Cloud Console; "
                "data lands ~24h after enabling."
            ),
        }

    # Prefer the detailed-export table (has resource-level rows) if present.
    table = next(
        (t for t in export_tables if "resource_v1" in t.table_id),
        export_tables[0],
    )
    table_ref = f"{project}.{_DATASET}.{table.table_id}"

    query = f"""
        SELECT
          service.description AS service,
          SUM(cost) AS gross_cost,
          SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS credits,
          SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net_cost,
          ANY_VALUE(currency) AS currency
        FROM `{table_ref}`
        WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
        GROUP BY service
        ORDER BY net_cost DESC
    """
    try:
        job_config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("days", "INT64", days)])
        rows = list(client.query(query, job_config=job_config).result())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Billing export query failed: %s", exc)
        return {"configured": False, "reason": f"Billing export query failed: {exc}"}

    by_service = []
    total_net = total_gross = total_credits = 0.0
    currency = "USD"
    for row in rows:
        net = float(row["net_cost"] or 0.0)
        gross = float(row["gross_cost"] or 0.0)
        credits = float(row["credits"] or 0.0)
        currency = row["currency"] or currency
        total_net += net
        total_gross += gross
        total_credits += credits
        by_service.append(
            {
                "service": row["service"] or "(unknown)",
                "net_usd": round(net, 4),
                "gross_usd": round(gross, 4),
                "credits_usd": round(credits, 4),
            }
        )

    return {
        "configured": True,
        "days": days,
        "currency": currency,
        "total_net_usd": round(total_net, 4),
        "total_gross_usd": round(total_gross, 4),
        "total_credits_usd": round(total_credits, 4),
        "by_service": by_service,
        "table": table_ref,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
