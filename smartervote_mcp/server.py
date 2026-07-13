"""SmarterVote MCP server backed by the races-api HTTP surface."""

from __future__ import annotations

import os
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from smartervote_mcp.client import RacesApiClient, compact_options

mcp = FastMCP("SmarterVote Races")


def _client() -> RacesApiClient:
    return RacesApiClient.from_env()


def _pipeline_options(**kwargs: Any) -> dict[str, Any]:
    """Build RunOptions for MCP tools, defaulting to cheap/economy mode.

    Non-economy model profiles can override cheap_mode downstream, so require an
    explicit cheap_mode=False opt-out before allowing them through.
    """
    requested_cheap_mode = kwargs.get("cheap_mode")
    model_profile = kwargs.get("model_profile")
    if requested_cheap_mode is not False and model_profile in {"balanced", "quality", "custom"}:
        raise ValueError(
            "Non-economy model_profile requires explicit cheap_mode=False. "
            "Omit model_profile or use model_profile='economy' for the default cheap run."
        )
    kwargs["cheap_mode"] = False if requested_cheap_mode is False else True
    return compact_options(**kwargs)


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
    baseline_source: Literal["latest", "published"] | None = None,
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
    runner: str | None = None,
) -> dict[str, Any]:
    """Queue one or more races for pipeline processing.

    Defaults to cheap/economy mode. Expensive default/quality/custom model
    profiles require explicitly passing cheap_mode=False. Pass runner="local" to
    route the runs to the long-lived local Docker worker instead of the default
    one-shot Cloud Run Job. Set baseline_source="published" for a targeted
    repair that must ignore any existing draft; the default "latest" behavior
    prefers a draft and falls back to published data.
    """
    options = _pipeline_options(
        cheap_mode=cheap_mode,
        force_fresh=force_fresh,
        baseline_source=baseline_source,
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
        runner=runner,
    )
    return await _client().post("/api/races/queue", json={"race_ids": race_ids, "options": options})


@mcp.tool()
async def run_race(
    race_id: str,
    cheap_mode: bool | None = True,
    force_fresh: bool | None = None,
    baseline_source: Literal["latest", "published"] | None = None,
    enabled_steps: list[str] | None = None,
    note: str | None = None,
    goal: str | None = None,
    runner: str | None = None,
) -> dict[str, Any]:
    """Queue a single race for pipeline processing.

    Defaults to cheap/economy mode. Expensive default/quality mode requires
    explicitly passing cheap_mode=False. Pass runner="local" to route the run to
    the long-lived local Docker worker; the deployed default is a one-shot Cloud
    Run Job. Set baseline_source="published" to ignore an existing draft when
    performing a targeted repair.
    """
    options = _pipeline_options(
        cheap_mode=cheap_mode,
        force_fresh=force_fresh,
        baseline_source=baseline_source,
        enabled_steps=enabled_steps,
        note=note,
        goal=goal,
        runner=runner,
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


# NOTE: trigger_web_deploy was removed. The Cloudflare Pages deploy already
# fires automatically on every push to main (cloudflare-deploy.yaml runs on
# workflow_run after CI), and the agent permission layer auto-denied the manual
# tool, so it was redundant and uninvokable in practice. Trigger a deploy with a
# normal git push, or `gh workflow run cloudflare-deploy.yaml` if a manual run is
# needed.


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


_US_STATES: dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
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
        if race_id.startswith(prefix) or race_state.upper() == abbr or full_name.lower() in jurisdiction.lower():
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
    model: str = "google/gemini-3.5-flash",
) -> dict[str, Any]:
    """Automatically generate chamber-level forecast narratives using an LLM on the remote races-api backend."""
    client = _client()
    res = await client.post("/api/races/chamber_forecasts/generate", json={"model": model})
    return {"success": True, "api_response": res}


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
