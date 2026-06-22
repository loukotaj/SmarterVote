"""SmarterVote MCP server backed by the races-api HTTP surface."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from smartervote_mcp.client import RacesApiClient, compact_options

mcp = FastMCP("SmarterVote Races")


def _client() -> RacesApiClient:
    return RacesApiClient.from_env()


@mcp.tool()
async def health() -> dict[str, Any]:
    """Check whether the configured races-api is reachable."""
    return await _client().get("/health")


@mcp.tool()
async def list_published_races() -> list[str]:
    """List public published race IDs."""
    return await _client().get("/races")


@mcp.tool()
async def list_race_summaries() -> list[dict[str, Any]]:
    """List public published race summaries for browsing and search."""
    return await _client().get("/races/summaries")


@mcp.tool()
async def get_published_race(race_id: str) -> dict[str, Any]:
    """Fetch full public RaceJSON for a published race ID."""
    return await _client().get(f"/races/{race_id}")


@mcp.tool()
async def list_admin_races() -> dict[str, Any]:
    """List admin race records, including status and storage metadata."""
    return await _client().get("/api/races")


@mcp.tool()
async def get_race_record(race_id: str) -> dict[str, Any]:
    """Fetch one admin race record from races-api."""
    return await _client().get(f"/api/races/{race_id}")


@mcp.tool()
async def list_draft_races() -> dict[str, Any]:
    """List draft race summaries."""
    return await _client().get("/api/races/drafts")


@mcp.tool()
async def list_pipeline_steps() -> dict[str, Any]:
    """List supported pipeline step IDs and labels."""
    return await _client().get("/steps")


@mcp.tool()
async def get_race_data(race_id: str, draft: bool = False) -> dict[str, Any]:
    """Fetch full RaceJSON from published data or drafts."""
    return await _client().get(f"/api/races/{race_id}/data", params={"draft": draft})


@mcp.tool()
async def queue_races(
    race_ids: list[str],
    cheap_mode: bool | None = True,
    force_fresh: bool | None = None,
    save_artifact: bool | None = None,
    enabled_steps: list[str] | None = None,
    research_model: str | None = None,
    claude_model: str | None = None,
    gemini_model: str | None = None,
    grok_model: str | None = None,
    model_profile: str | None = None,
    model_overrides: dict[str, str] | None = None,
    review_providers: list[str] | None = None,
    max_candidates: int | None = None,
    candidate_names: list[str] | None = None,
    target_no_info: bool | None = None,
    note: str | None = None,
    goal: str | None = None,
) -> dict[str, Any]:
    """Queue one or more races for pipeline processing."""
    options = compact_options(
        cheap_mode=cheap_mode,
        force_fresh=force_fresh,
        save_artifact=save_artifact,
        enabled_steps=enabled_steps,
        research_model=research_model,
        claude_model=claude_model,
        gemini_model=gemini_model,
        grok_model=grok_model,
        model_profile=model_profile,
        model_overrides=model_overrides,
        review_providers=review_providers,
        max_candidates=max_candidates,
        candidate_names=candidate_names,
        target_no_info=target_no_info,
        note=note,
        goal=goal,
    )
    return await _client().post("/api/races/queue", json={"race_ids": race_ids, "options": options})


@mcp.tool()
async def run_race(
    race_id: str,
    cheap_mode: bool | None = True,
    force_fresh: bool | None = None,
    enabled_steps: list[str] | None = None,
    note: str | None = None,
    goal: str | None = None,
) -> dict[str, Any]:
    """Queue a single race for pipeline processing."""
    options = compact_options(
        cheap_mode=cheap_mode,
        force_fresh=force_fresh,
        enabled_steps=enabled_steps,
        note=note,
        goal=goal,
    )
    return await _client().post(f"/api/races/{race_id}/run", json=options)


@mcp.tool()
async def publish_race(race_id: str) -> dict[str, Any]:
    """Publish a draft race."""
    return await _client().post(f"/api/races/{race_id}/publish")


@mcp.tool()
async def publish_races(race_ids: list[str]) -> dict[str, Any]:
    """Publish multiple draft races in bulk."""
    return await _client().post("/api/races/publish", json={"race_ids": race_ids})


@mcp.tool()
async def list_unpublished_drafts() -> list[dict[str, Any]]:
    """List all draft races that are either not published or have unpublished changes."""
    res = await list_admin_races()
    races = res.get("races", [])
    unpublished = []
    for race in races:
        if race.get("draft_exists") and (not race.get("published_exists") or race.get("has_unpublished_changes")):
            unpublished.append(race)
    return unpublished


@mcp.tool()
async def trigger_web_deploy() -> dict[str, Any]:
    """Trigger the Cloudflare Pages GitHub Actions workflow using the local gh CLI."""
    import subprocess

    workflow = "cloudflare-deploy.yaml"
    try:
        result = subprocess.run(["gh", "workflow", "run", workflow], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return {"success": True, "message": f"Successfully triggered {workflow} workflow."}
        else:
            return {
                "success": False,
                "error": f"Failed to run workflow. returncode={result.returncode}",
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@mcp.tool()
async def unpublish_race(race_id: str) -> dict[str, Any]:
    """Remove a race from public published data while keeping its draft."""
    return await _client().post(f"/api/races/{race_id}/unpublish")


@mcp.tool()
async def recheck_race(race_id: str) -> dict[str, Any]:
    """Reconcile one race status from storage and Firestore state."""
    return await _client().post(f"/api/races/{race_id}/recheck")


@mcp.tool()
async def recheck_all_races() -> dict[str, Any]:
    """Reconcile all race statuses from storage and Firestore state."""
    return await _client().post("/api/races/recheck")


@mcp.tool()
async def repair_inconsistent_race_statuses(limit: int = 50) -> dict[str, Any]:
    """Repair races where status disagrees with draft/published catalog flags.

    This avoids the heavier global recheck endpoint by rechecking only obviously
    inconsistent races one-by-one.
    """
    res = await list_admin_races()
    races = res.get("races", []) if isinstance(res, dict) else []
    inconsistent = []
    for race in races:
        status = str(race.get("status") or "")
        published_exists = bool(race.get("published_exists"))
        draft_exists = bool(race.get("draft_exists"))
        if status == "empty" and (published_exists or draft_exists):
            inconsistent.append(str(race.get("race_id") or race.get("id") or ""))
        elif status == "draft" and published_exists:
            inconsistent.append(str(race.get("race_id") or race.get("id") or ""))

    repaired = []
    failed = []
    for race_id in [rid for rid in inconsistent if rid][: max(1, limit)]:
        try:
            result = await recheck_race(race_id)
            race = result.get("race", {}) if isinstance(result, dict) else {}
            repaired.append({"race_id": race_id, "status": race.get("status")})
        except Exception as exc:
            failed.append({"race_id": race_id, "error": str(exc)})

    return {
        "checked": min(len(inconsistent), max(1, limit)),
        "inconsistent_total": len(inconsistent),
        "repaired": repaired,
        "failed": failed,
    }


_US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}
_STATE_NAME_TO_ABBR: dict[str, str] = {v.lower(): k for k, v in _US_STATES.items()}


def _normalize_state(query: str) -> tuple[str, str]:
    """Return (abbreviation, full_name) for a state query string."""
    q = query.strip()
    upper = q.upper()
    if upper in _US_STATES:
        return upper, _US_STATES[upper]
    lower = q.lower()
    if lower in _STATE_NAME_TO_ABBR:
        abbr = _STATE_NAME_TO_ABBR[lower]
        return abbr, _US_STATES[abbr]
    raise ValueError(f"Unknown US state: {query!r}")


@mcp.tool()
async def list_races_by_state(state: str) -> list[dict[str, Any]]:
    """List admin races that belong to a given US state.

    Accepts state abbreviation (e.g. 'ND') or full name (e.g. 'North Dakota').
    """
    abbr, full_name = _normalize_state(state)
    prefix = abbr.lower() + "-"
    res = await list_admin_races()
    races = res.get("races", []) if isinstance(res, dict) else []
    filtered = []
    for race in races:
        race_id = str(race.get("race_id") or race.get("id") or "")
        race_state = str(race.get("state") or "")
        jurisdiction = str(race.get("jurisdiction") or "")
        if (
            race_id.startswith(prefix)
            or race_state.upper() == abbr
            or full_name.lower() in jurisdiction.lower()
        ):
            filtered.append(race)
    return filtered


@mcp.tool()
async def delete_race(race_id: str) -> dict[str, Any]:
    """Permanently delete a race record, all GCS drafts/published files, and its Firestore entry.

    This is irreversible. Use unpublish_race instead if you only want to hide a race from public view.
    """
    return await _client().delete(f"/api/races/{race_id}")


@mcp.tool()
async def delete_draft(race_id: str) -> dict[str, Any]:
    """Delete only the draft version of a race from GCS, keeping the published page and Firestore record."""
    return await _client().delete(f"/api/races/{race_id}/draft")


@mcp.tool()
async def sleep(seconds: float) -> dict[str, Any]:
    """Pause execution for the given number of seconds (max 300).

    Useful for waiting between polling operations, rate-limiting retries, or giving the pipeline
    time to process before checking results.
    """
    import asyncio

    clamped = min(max(0, seconds), 300)
    await asyncio.sleep(clamped)
    return {"slept_seconds": clamped}


@mcp.tool()
async def cancel_race(race_id: str) -> dict[str, Any]:
    """Cancel a queued or running race."""
    return await _client().post(f"/api/races/{race_id}/cancel")


@mcp.tool()
async def get_queue(active_only: bool = False, limit: int = 200) -> dict[str, Any]:
    """List queue items."""
    return await _client().get("/api/queue", params={"active_only": active_only, "limit": limit})


@mcp.tool()
async def list_runs(limit: int = 50) -> dict[str, Any]:
    """List recent pipeline runs."""
    return await _client().get("/runs", params={"limit": limit})


@mcp.tool()
async def list_active_runs() -> dict[str, Any]:
    """List currently pending or running pipeline runs."""
    return await _client().get("/runs/active")


@mcp.tool()
async def get_run(run_id: str) -> dict[str, Any]:
    """Fetch a pipeline run record."""
    return await _client().get(f"/runs/{run_id}")


@mcp.tool()
async def get_run_logs(run_id: str, since: int = 0) -> dict[str, Any]:
    """Fetch run logs, optionally after an existing log count."""
    return await _client().get(f"/runs/{run_id}/logs", params={"since": since})


@mcp.tool()
async def cancel_or_delete_run(run_id: str) -> dict[str, Any]:
    """Cancel an active run or delete a finished run record."""
    return await _client().delete(f"/runs/{run_id}")


@mcp.tool()
async def get_pipeline_metrics(limit: int = 50) -> dict[str, Any]:
    """Return recent pipeline cost/token records."""
    return await _client().get("/pipeline/metrics", params={"limit": limit})


@mcp.tool()
async def get_pipeline_metrics_summary() -> dict[str, Any]:
    """Return aggregate pipeline cost stats."""
    return await _client().get("/pipeline/metrics/summary")


@mcp.tool()
async def clear_races_api_cache() -> dict[str, Any]:
    """Clear the races-api in-memory response cache."""
    return await _client().post("/cache/clear")


@mcp.tool()
async def get_analytics_overview(hours: int = 24) -> dict[str, Any]:
    """Fetch request analytics overview for the last N hours."""
    return await _client().get("/analytics/overview", params={"hours": hours})


@mcp.tool()
async def get_race_analytics(hours: int = 24) -> dict[str, Any]:
    """Fetch per-race request analytics for the last N hours."""
    return await _client().get("/analytics/races", params={"hours": hours})


@mcp.tool()
async def get_analytics_timeseries(hours: int = 24, bucket_minutes: int = 60) -> dict[str, Any]:
    """Fetch bucketed request analytics for charting."""
    return await _client().get("/analytics/timeseries", params={"hours": hours, "bucket": bucket_minutes})


@mcp.tool()
async def get_traffic_analytics(hours: int = 24) -> dict[str, Any]:
    """Fetch static-site page views, visits, pages, referrers, countries, and devices."""
    return await _client().get("/analytics/traffic", params={"hours": hours})


@mcp.resource("smartervote://races/summaries")
async def race_summaries_resource() -> list[dict[str, Any]]:
    """Published race summaries."""
    return await list_race_summaries()


@mcp.resource("smartervote://races/{race_id}")
async def published_race_resource(race_id: str) -> dict[str, Any]:
    """Published RaceJSON by race ID."""
    return await get_published_race(race_id)


@mcp.prompt()
def review_race_prompt(race_id: str) -> str:
    """Prompt for reviewing a SmarterVote race record."""
    return (
        f"Review SmarterVote race `{race_id}`. Load the published race data and, if available, "
        "the draft/admin record. Focus on stale sources, missing candidate data, low-confidence "
        "issue positions, and whether the race should be rerun."
    )


@mcp.tool()
async def update_chamber_forecasts(
    house_narrative: str,
    senate_narrative: str,
    governors_narrative: str,
    chambers: dict[str, Any] | None = None,
    schema_version: str | None = None,
) -> dict[str, Any]:
    """Manually update the chamber-level forecast narratives."""
    payload = {
        "house_narrative": house_narrative,
        "senate_narrative": senate_narrative,
        "governors_narrative": governors_narrative,
    }
    if chambers is not None:
        payload["chambers"] = chambers
    if schema_version is not None:
        payload["schema_version"] = schema_version
    return await _client().post("/api/races/chamber_forecasts", json=payload)


def _published_data_dir() -> "Path":
    from pathlib import Path

    return Path(__file__).resolve().parents[1] / "data" / "published"


def _load_local_published_summaries() -> list[dict[str, Any]]:
    import json

    summaries_path = _published_data_dir() / "summaries.json"
    with summaries_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise RuntimeError(f"Expected {summaries_path} to contain a list")
    return data


def _is_us_senate_summary(race: dict[str, Any]) -> bool:
    return str(race.get("office") or "") in {"United States Senate", "U.S. Senate"}


async def _hydrate_missing_senate_summary_forecasts(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill missing Senate summary forecasts from full published RaceJSON records."""
    from shared.race_catalog import build_forecast_summary

    hydrated = []
    client = _client()
    for race in summaries:
        if not _is_us_senate_summary(race) or race.get("forecast"):
            continue
        race_id = str(race.get("id") or race.get("race_id") or "")
        if not race_id:
            continue
        full_race = await client.get(f"/races/{race_id}")
        forecast = build_forecast_summary(full_race) if isinstance(full_race, dict) else None
        if forecast:
            race["forecast"] = forecast
            hydrated.append(race_id)
    return hydrated


@mcp.tool()
async def generate_static_chamber_forecasts(source: str = "api") -> dict[str, Any]:
    """Generate data/published/chamber_forecasts.json from published summaries.

    Use source="api" to read live published summaries through races-api, or
    source="local" to use data/published/summaries.json. This does not publish
    or deploy anything by itself.
    """
    import json

    from shared.forecast_summary import build_chamber_forecasts

    if source == "local":
        summaries = _load_local_published_summaries()
    elif source == "api":
        summaries = await _client().get("/races/summaries")
        await _hydrate_missing_senate_summary_forecasts(summaries)
    else:
        raise ValueError('source must be "api" or "local"')
    if not isinstance(summaries, list):
        raise RuntimeError(f"Expected a list of summaries, got {type(summaries)}")
    data = build_chamber_forecasts(summaries)
    output_path = _published_data_dir() / "chamber_forecasts.json"
    output_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {
        "success": True,
        "path": str(output_path),
        "updated_at": data["updated_at"],
        "senate": data["chambers"]["senate"],
    }


@mcp.tool()
async def refresh_static_race_summaries() -> dict[str, Any]:
    """Refresh data/published/summaries.json from live published races-api summaries."""
    import json

    summaries = await _client().get("/races/summaries")
    if not isinstance(summaries, list):
        raise RuntimeError(f"Expected a list of summaries, got {type(summaries)}")
    hydrated_forecasts = await _hydrate_missing_senate_summary_forecasts(summaries)
    output_path = _published_data_dir() / "summaries.json"
    output_path.write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    senate_forecast_count = sum(
        1 for race in summaries if "senate" in str(race.get("office") or "").lower() and race.get("forecast")
    )
    return {
        "success": True,
        "path": str(output_path),
        "summary_count": len(summaries),
        "senate_forecast_count": senate_forecast_count,
        "hydrated_senate_forecasts": hydrated_forecasts,
    }


@mcp.tool()
async def refresh_static_forecast_data() -> dict[str, Any]:
    """Refresh summaries.json from live API, then regenerate chamber_forecasts.json locally."""
    summaries_result = await refresh_static_race_summaries()
    chamber_result = await generate_static_chamber_forecasts(source="local")
    return {"success": True, "summaries": summaries_result, "chamber_forecasts": chamber_result}


@mcp.tool()
async def publish_chamber_forecasts() -> dict[str, Any]:
    """Publish the remotely saved draft chamber forecasts (copy draft -> published)."""
    res = await _client().post("/api/races/chamber_forecasts/publish")
    return {"success": True, "api_response": res}


@mcp.tool()
async def review_chamber_forecast_drafts() -> dict[str, Any]:
    """Compare the draft chamber forecasts against the published ones to highlight changes."""
    client = _client()
    try:
        draft = await client.get("/api/races/chamber_forecasts/draft")
    except Exception as e:
        return {"success": False, "error": f"Failed to load draft forecasts: {e}"}

    try:
        published = await client.get("/races/chamber_forecasts")
    except Exception:
        published = None

    if not published:
        return {"draft": draft, "message": "No published forecasts found. Draft represents first-time narrative."}

    # Build comparisons
    changes = {}
    for chamber_id in ["house", "senate", "governors"]:
        draft_ch = draft.get("chambers", {}).get(chamber_id, {})
        pub_ch = published.get("chambers", {}).get(chamber_id, {})

        changes[chamber_id] = {
            "control_party": {
                "before": pub_ch.get("control_party"),
                "after": draft_ch.get("control_party"),
            },
            "control_probability": {
                "before": pub_ch.get("control_probability"),
                "after": draft_ch.get("control_probability"),
            },
            "expected_seats": {
                "before": pub_ch.get("expected_seats"),
                "after": draft_ch.get("expected_seats"),
            },
            "narrative_changed": pub_ch.get("narrative") != draft_ch.get("narrative"),
        }

    return {"changes": changes, "draft": draft, "published": published}


@mcp.tool()
async def generate_chamber_forecasts(
    model: str = "google/gemini-2.5-flash",
) -> dict[str, Any]:
    """Automatically generate chamber-level forecast narratives using an LLM on the remote races-api backend."""
    client = _client()
    res = await client.post("/api/races/chamber_forecasts/generate", json={"model": model})
    return {"success": True, "api_response": res}


@mcp.tool()
async def audit_senate_forecast_data() -> dict[str, Any]:
    """Audit published Senate race forecasts for completeness and freshness.
    Returns counts of missing or stale forecasts and list of target race IDs.
    """
    summaries = await _client().get("/races/summaries")
    if not isinstance(summaries, list):
        return {"success": False, "error": "Invalid summaries from API"}

    senate_races = [r for r in summaries if "senate" in str(r.get("office") or "").lower()]

    missing_forecast = []
    stale_forecast = []
    complete_count = 0

    for r in senate_races:
        race_id = r.get("id") or r.get("race_id")
        forecast = r.get("forecast")
        if not forecast:
            missing_forecast.append(race_id)
        else:
            generated_at = forecast.get("generated_at")
            updated_utc = r.get("updated_utc")
            if generated_at and updated_utc:
                try:
                    gen_str = generated_at.replace("Z", "").split(".")[0]
                    up_str = updated_utc.replace("Z", "").split(".")[0]
                    if gen_str < up_str:
                        stale_forecast.append(race_id)
                    else:
                        complete_count += 1
                except Exception:
                    complete_count += 1
            else:
                complete_count += 1

    return {
        "total_senate_races": len(senate_races),
        "complete_forecasts_count": complete_count,
        "missing_forecast_count": len(missing_forecast),
        "missing_forecast_race_ids": missing_forecast,
        "stale_forecast_count": len(stale_forecast),
        "stale_forecast_race_ids": stale_forecast,
    }


@mcp.tool()
async def queue_senate_forecast_reruns(
    race_ids: list[str], force_fresh: bool | None = None, model_profile: str | None = None, note: str | None = None
) -> dict[str, Any]:
    """Queue only the forecast step for selected Senate races (defaults to draft-only output)."""
    return await queue_races(
        race_ids=race_ids,
        cheap_mode=True,
        force_fresh=force_fresh,
        enabled_steps=["forecast"],
        model_profile=model_profile,
        note=note or "Senate Forecast Rerun",
    )


@mcp.tool()
async def monitor_senate_forecast_reruns(run_ids: list[str]) -> dict[str, Any]:
    """Check the status of a list of forecast rerun runs."""
    completed = []
    running = []
    failed = []

    for rid in run_ids:
        try:
            run_data = await get_run(rid)
            status = run_data.get("status")
            if status in ("completed", "skipped"):
                completed.append(rid)
            elif status in ("failed", "cancelled"):
                failed.append({"run_id": rid, "error": run_data.get("error")})
            else:
                running.append(rid)
        except Exception as e:
            failed.append({"run_id": rid, "error": str(e)})

    return {"completed": completed, "running": running, "failed": failed, "all_finished": len(running) == 0}


@mcp.tool()
async def review_senate_forecast_drafts() -> dict[str, Any]:
    """Compare Senate draft forecasts against currently published ones to highlight changes."""
    summaries = await _client().get("/races/summaries")
    if not isinstance(summaries, list):
        return {"success": False, "error": "Invalid summaries from API"}

    senate_races = [r for r in summaries if "senate" in str(r.get("office") or "").lower()]

    comparisons = []
    for r in senate_races:
        race_id = r.get("id") or r.get("race_id")
        try:
            draft_data = await _client().get(f"/api/races/{race_id}/data", params={"draft": True})
            published_data = await _client().get(f"/api/races/{race_id}/data", params={"draft": False})

            draft_fc = draft_data.get("forecast") or {}
            pub_fc = published_data.get("forecast") or {}

            if draft_fc.get("rating") != pub_fc.get("rating") or draft_fc.get("win_probability") != pub_fc.get(
                "win_probability"
            ):
                comparisons.append(
                    {
                        "race_id": race_id,
                        "published": {
                            "winner_party": pub_fc.get("predicted_winner_party"),
                            "win_probability": pub_fc.get("win_probability"),
                            "rating": pub_fc.get("rating"),
                        },
                        "draft": {
                            "winner_party": draft_fc.get("predicted_winner_party"),
                            "win_probability": draft_fc.get("win_probability"),
                            "rating": draft_fc.get("rating"),
                        },
                    }
                )
        except Exception:
            continue

    return {"changed_races_count": len(comparisons), "comparisons": comparisons}


@mcp.tool()
async def validate_static_chamber_forecasts() -> dict[str, Any]:
    """Validate the local static chamber_forecasts.json file before publishing."""
    import json

    path = _published_data_dir() / "chamber_forecasts.json"
    if not path.exists():
        return {"success": False, "error": f"File does not exist at {path}"}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _validate_chamber_forecast_payload(data)
    except Exception as e:
        return {"success": False, "error": f"Validation error: {e}"}


def _validate_chamber_forecast_payload(data: dict[str, Any]) -> dict[str, Any]:
    schema_version = data.get("schema_version")
    if schema_version != "chamber_forecasts.v2":
        return {"success": False, "error": f"Expected schema_version chamber_forecasts.v2, got {schema_version}"}

    chambers = data.get("chambers", {})
    expected_totals = {"house": 435, "senate": 100, "governors": 50}
    required_fields = [
        "seat_distribution",
        "bottom_line",
        "why_party_favored",
        "opposing_party_path",
        "key_uncertainty",
    ]

    summary: dict[str, Any] = {}
    for chamber_id, expected_total in expected_totals.items():
        chamber = chambers.get(chamber_id, {})
        if not chamber:
            return {"success": False, "error": f"{chamber_id} chamber forecast missing"}

        projected = chamber.get("projected_seats", {})
        total_projected = sum(projected.values())
        if total_projected != expected_total:
            return {
                "success": False,
                "error": f"{chamber_id} projected seats must sum to {expected_total}, got {total_projected}",
            }

        for field in required_fields:
            if field not in chamber:
                return {"success": False, "error": f"{chamber_id} chamber forecast missing required field: {field}"}
        if not chamber.get("seat_distribution"):
            return {"success": False, "error": f"{chamber_id} chamber forecast must include seat_distribution data"}

        summary[chamber_id] = {
            "control_party": chamber.get("control_party"),
            "projected_seats": projected,
            "expected_seats": chamber.get("expected_seats"),
            "seat_distribution_count": len(chamber.get("seat_distribution") or {}),
        }

    senate = chambers["senate"]
    if senate.get("vp_tiebreak_party") != "Republican":
        return {"success": False, "error": "Senate chamber forecast missing Republican VP tie-break assumption"}
    senate_projected = senate.get("projected_seats", {})
    if senate_projected.get("Democratic") == 50 and senate_projected.get("Republican") == 50:
        if senate.get("control_party") != "Republican":
            return {"success": False, "error": "Senate 50-50 projected split must result in Republican control"}

    return {"success": True, "message": "Chamber forecasts validation passed successfully.", "chambers": summary}


@mcp.tool()
async def publish_static_forecast_bundle(dry_run: bool = False) -> dict[str, Any]:
    """Refresh static summaries, save the generated chamber forecast as a remote draft, and publish it."""
    import json

    refresh_res = await refresh_static_forecast_data()
    val_res = await validate_static_chamber_forecasts()

    if not val_res.get("success"):
        return {"success": False, "error": "Validation failed, bundle not published", "validation": val_res}

    if dry_run:
        return {"success": True, "message": "Dry-run validation successful. Bundle not published.", "refresh": refresh_res}

    path = _published_data_dir() / "chamber_forecasts.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    draft_res = await update_chamber_forecasts(
        house_narrative=str(data.get("house") or ""),
        senate_narrative=str(data.get("senate") or ""),
        governors_narrative=str(data.get("governors") or ""),
        chambers=data.get("chambers"),
        schema_version=str(data.get("schema_version") or "chamber_forecasts.v2"),
    )
    pub_res = await publish_chamber_forecasts()
    return {"success": True, "refresh": refresh_res, "validation": val_res, "draft": draft_res, "publish": pub_res}


@mcp.tool()
async def verify_live_forecast_page_data() -> dict[str, Any]:
    """Check deployed or local live static endpoints and verify forecast bundle properties."""
    try:
        data = await _client().get("/races/chamber_forecasts")
        validation = _validate_chamber_forecast_payload(data)
        if not validation.get("success"):
            return validation
        return {
            "success": True,
            "schema_version": data.get("schema_version"),
            "updated_at": data.get("updated_at"),
            "chambers": validation.get("chambers"),
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to connect to API: {e}"}


def main() -> None:
    """Run the MCP server."""
    transport = os.getenv("SMARTERVOTE_MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
