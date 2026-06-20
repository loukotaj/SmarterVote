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
        result = subprocess.run(["gh", "workflow", "run", "WebDeploy.yml"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return {"success": True, "message": "Successfully triggered WebDeploy.yml workflow."}
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


@mcp.tool()
async def list_north_dakota_races() -> list[dict[str, Any]]:
    """List admin races that appear to belong to North Dakota."""
    res = await list_admin_races()
    races = res.get("races", []) if isinstance(res, dict) else []
    filtered = []
    for race in races:
        race_id = str(race.get("race_id") or race.get("id") or "")
        state = str(race.get("state") or "")
        jurisdiction = str(race.get("jurisdiction") or "")
        if race_id.startswith("nd-") or state.upper() == "ND" or "north dakota" in jurisdiction.lower():
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
) -> dict[str, Any]:
    """Manually update the chamber-level forecast narratives."""
    payload = {
        "house_narrative": house_narrative,
        "senate_narrative": senate_narrative,
        "governors_narrative": governors_narrative,
    }
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
        1
        for race in summaries
        if "senate" in str(race.get("office") or "").lower() and race.get("forecast")
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
async def publish_static_chamber_forecasts() -> dict[str, Any]:
    """Publish local data/published/chamber_forecasts.json through the races-api admin endpoint."""
    import json

    path = _published_data_dir() / "chamber_forecasts.json"
    if not path.exists():
        generated = await generate_static_chamber_forecasts()
        path = _published_data_dir() / "chamber_forecasts.json"
    else:
        generated = None
    data = json.loads(path.read_text(encoding="utf-8"))
    payload = {
        "schema_version": data.get("schema_version"),
        "house_narrative": data.get("house") or data.get("chambers", {}).get("house", {}).get("narrative", ""),
        "senate_narrative": data.get("senate") or data.get("chambers", {}).get("senate", {}).get("narrative", ""),
        "governors_narrative": data.get("governors") or data.get("chambers", {}).get("governors", {}).get("narrative", ""),
        "chambers": data.get("chambers"),
    }
    save_res = await _client().post("/api/races/chamber_forecasts", json=payload)
    return {"success": True, "generated": generated, "save_response": save_res}


@mcp.tool()
async def generate_chamber_forecasts(
    model: str = "google/gemini-2.5-flash",
) -> dict[str, Any]:
    """Automatically generate chamber-level forecast narratives using an LLM over published race summaries and save them."""
    import logging
    logger = logging.getLogger("smartervote_mcp.generate")

    # 1. Fetch all published race summaries
    client = _client()
    summaries = await client.get("/races/summaries")
    if not isinstance(summaries, list):
        raise RuntimeError(f"Expected a list of summaries, got {type(summaries)}")

    # 2. Group races by chamber
    senate_races = []
    house_races = []
    governor_races = []

    for r in summaries:
        office = (r.get("office") or "").lower()
        if "senate" in office:
            senate_races.append(r)
        elif "house" in office or "representative" in office:
            house_races.append(r)
        elif "governor" in office or "gubernatorial" in office:
            governor_races.append(r)

    # Helper to build summaries text
    def build_chamber_context(races: list[dict[str, Any]], name: str) -> str:
        if not races:
            return f"No published races found for the {name}."

        dem_wins = 0
        gop_wins = 0
        toss_ups = 0
        competitive_list = []

        for r in races:
            forecast = r.get("forecast") or {}
            rating = (forecast.get("rating") or "").lower()
            winner_party = (forecast.get("predicted_winner_party") or "").lower()
            prob = forecast.get("win_probability") or 0.5
            title = r.get("title") or r.get("id")

            if "toss-up" in rating or "tossup" in rating:
                toss_ups += 1
                competitive_list.append(f"- {title}: Toss-up (Win Prob: {prob*100:.1f}%)")
            elif "lean" in rating:
                competitive_list.append(f"- {title}: Lean {winner_party.upper()} (Win Prob: {prob*100:.1f}%)")
                if "d" in winner_party:
                    dem_wins += 1
                elif "r" in winner_party:
                    gop_wins += 1
            elif "likely" in rating:
                competitive_list.append(f"- {title}: Likely {winner_party.upper()} (Win Prob: {prob*100:.1f}%)")
                if "d" in winner_party:
                    dem_wins += 1
                elif "r" in winner_party:
                    gop_wins += 1
            elif "safe" in rating:
                if "d" in winner_party:
                    dem_wins += 1
                elif "r" in winner_party:
                    gop_wins += 1

        lines = [
            f"Chamber: {name}",
            f"Total Published Races: {len(races)}",
            f"Toss-up Races: {toss_ups}",
            f"Projected Democratic Wins (among published non-tossups): {dem_wins}",
            f"Projected Republican Wins (among published non-tossups): {gop_wins}",
            "\nCompetitive/Notable Races Detail:"
        ]
        lines.extend(competitive_list[:30])
        return "\n".join(lines)

    # 3. Call LLM for each chamber
    from pipeline_client.agent.llm import _call_openrouter

    async def get_narrative(chamber_name: str, context_text: str) -> str:
        system_prompt = (
            "You are a professional, nonpartisan, highly analytical election forecaster (like Cook Political Report, FiveThirtyEight, or Split Ticket). "
            f"Your goal is to write a concise, 2-3 sentence overview narrative summarizing the battle for control "
            f"of the {chamber_name} in the 2026 election cycle, based on the forecast data provided. "
            "Focus on the big picture: which party is favored to win or retain control, the size of their projected majority "
            "(if clear), the number of toss-up/competitive seats, and key battlegrounds. "
            "Keep it sober, analytical, and objective. Avoid generic filler. Do not mention that you are an AI. "
            "Do not use markdown formatting (like lists, bolding, or headers), just write 2-3 well-crafted sentences."
        )
        user_prompt = f"Here is the aggregated forecast data for the {chamber_name}:\n\n{context_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            resp = await _call_openrouter(messages=messages, model=model)
            narrative = resp.choices[0].message.content.strip()
            return narrative
        except Exception as e:
            logger.warning(f"Error calling LLM for {chamber_name}: {e}")
            return f"Model projections indicate a highly competitive battle for control of the {chamber_name}."

    senate_narrative = await get_narrative("US Senate", build_chamber_context(senate_races, "US Senate"))
    house_narrative = await get_narrative("US House", build_chamber_context(house_races, "US House"))
    governors_narrative = await get_narrative("Governors", build_chamber_context(governor_races, "Governors"))

    from shared.forecast_summary import build_chamber_forecasts

    forecast_data = build_chamber_forecasts(
        summaries,
        {
            "house": house_narrative,
            "senate": senate_narrative,
            "governors": governors_narrative,
        },
    )

    # 4. Save via POST endpoint
    payload = {
        "schema_version": forecast_data.get("schema_version"),
        "house_narrative": forecast_data["house"],
        "senate_narrative": forecast_data["senate"],
        "governors_narrative": forecast_data["governors"],
        "chambers": forecast_data.get("chambers"),
    }

    save_res = await client.post("/api/races/chamber_forecasts", json=payload)
    return {
        "success": True,
        "forecast": forecast_data,
        "save_response": save_res
    }


def main() -> None:
    """Run the MCP server."""
    transport = os.getenv("SMARTERVOTE_MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
