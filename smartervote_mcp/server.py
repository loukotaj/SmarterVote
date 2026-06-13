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
    """Trigger the WebDeploy.yml GitHub Actions workflow using the local gh CLI.
    This redeploys the static site to smarter.vote.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["gh", "workflow", "run", "WebDeploy.yml"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            return {"success": True, "message": "Successfully triggered WebDeploy.yml workflow."}
        else:
            return {
                "success": False,
                "error": f"Failed to run workflow. returncode={result.returncode}",
                "stdout": result.stdout,
                "stderr": result.stderr
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


def main() -> None:
    """Run the MCP server."""
    transport = os.getenv("SMARTERVOTE_MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
