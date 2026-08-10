"""SmarterVote MCP server backed by the races-api HTTP surface."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Dict, List, Literal, Tuple
from urllib.parse import unquote

from mcp.server.fastmcp import FastMCP

from shared.model_catalog import DEFAULT_CHAMBER_FORECAST_MODEL
from smartervote_mcp.client import RacesApiClient, compact_options

mcp = FastMCP("SmarterVote Races")


def _client() -> RacesApiClient:
    return RacesApiClient.from_env()


def _pipeline_options(**kwargs: Any) -> Dict[str, Any]:
    """Build RunOptions for MCP tools, defaulting to the cheap `default` profile.

    Anything above `default` costs materially more per race, and a profile name
    alone can raise spend without the caller ever saying so. Require an explicit
    ``cheap_mode=False`` as the sign-off. Retired profile names are still
    rejected the same way, since they map forward onto `premium`.
    """
    requested_cheap_mode = kwargs.get("cheap_mode")
    model_profile = kwargs.get("model_profile")
    if requested_cheap_mode is not False and model_profile in {"premium", "custom", "balanced", "quality"}:
        raise ValueError(
            "model_profile above 'default' requires explicit cheap_mode=False. "
            "Omit model_profile or use model_profile='default' for the standard cheap run."
        )
    kwargs["cheap_mode"] = False if requested_cheap_mode is False else True
    return compact_options(**kwargs)


@mcp.tool(structured_output=False)
async def health() -> Dict[str, Any]:
    """Check whether the configured races-api is reachable."""
    return await _client().get("/health")


@mcp.tool(structured_output=False)
async def list_published_races() -> List[str]:
    """List public published race IDs."""
    return await _client().get("/races")


@mcp.tool(structured_output=False)
async def list_race_summaries() -> List[Dict[str, Any]]:
    """List public published race summaries for browsing and search."""
    return await _client().get("/races/summaries")


@mcp.tool(structured_output=False)
async def get_published_race(race_id: str) -> Dict[str, Any]:
    """Fetch full public RaceJSON for a published race ID."""
    return await _client().get(f"/races/{race_id}")


@mcp.tool(structured_output=False)
async def list_admin_races() -> Dict[str, Any]:
    """List admin race records, including status and storage metadata."""
    return await _client().get("/api/races")


def _missing_image_count(race: Dict[str, Any]) -> int:
    candidates = race.get("candidates") if isinstance(race.get("candidates"), list) else []
    return sum(
        1
        for candidate in candidates
        if isinstance(candidate, dict)
        and (not candidate.get("image_url") or "submitphoto-150px" in str(candidate.get("image_url") or "").lower())
    )


def _catalog_research_tier(race: Dict[str, Any]) -> str:
    health = race.get("catalog_health")
    if isinstance(health, dict) and health.get("research_tier"):
        return str(health["research_tier"])
    grade = str(race.get("quality_grade") or "").upper()
    if grade in {"A", "B"}:
        return "validated"
    if grade in {"C", "D", "F"}:
        return "graded_low"
    return "discovery_only"


async def _optional_api_get(path: str, *, params: Dict[str, Any]) -> Dict[str, Any]:
    """Return an optional analytics payload without making catalog scans brittle."""
    try:
        response = await _client().get(path, params=params)
        return response if isinstance(response, dict) else {}
    except Exception:
        return {}


def _race_pageviews(traffic: Dict[str, Any]) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for page in traffic.get("top_pages", []):
        if not isinstance(page, dict):
            continue
        match = re.match(r"^/races/([^/?#]+)", str(page.get("name") or ""))
        if not match:
            continue
        race_id = unquote(match.group(1))
        try:
            pageviews = max(0, int(page.get("pageviews") or 0))
        except (TypeError, ValueError):
            pageviews = 0
        totals[race_id] = totals.get(race_id, 0) + pageviews
    return totals


@mcp.tool(structured_output=False)
async def scan_catalog(
    state: str | None = None,
    office: str | None = None,
    publication: Literal["all", "published", "unpublished"] = "all",
    research_tier: Literal[
        "all",
        "validated",
        "graded_low",
        "discovery_only",
        "partial_research",
        "full_unreviewed",
        "empty",
    ] = "all",
    missing_images_only: bool = False,
    competitive_only: bool = False,
    traffic_hours: int = 720,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """Return a compact, ranked catalog-health scan without full RaceJSON payloads.

    This is the preferred inventory tool for deciding which races merit repair.
    It derives explicit research tiers, image gaps, competitiveness, freshness,
    and a deterministic priority score from the admin catalog.
    """
    traffic_hours = max(1, min(traffic_hours, 720))
    response, traffic, api_analytics = await asyncio.gather(
        list_admin_races(),
        _optional_api_get("/analytics/traffic", params={"hours": traffic_hours}),
        _optional_api_get("/analytics/races", params={"hours": traffic_hours}),
    )
    races = response.get("races", []) if isinstance(response, dict) else []
    pageviews_by_race = _race_pageviews(traffic)
    requests_by_race = {
        str(item.get("race_id")): int(item.get("requests_24h") or 0)
        for item in api_analytics.get("races", [])
        if isinstance(item, dict) and item.get("race_id")
    }
    rows: List[Dict[str, Any]] = []
    competitive_ratings = {"tossup", "tilt_d", "tilt_r", "lean_d", "lean_r"}
    state_query = str(state or "").strip().lower()
    office_query = str(office or "").strip().lower()

    for race in races:
        if not isinstance(race, dict):
            continue
        published = bool(race.get("published_exists"))
        tier = _catalog_research_tier(race)
        health = race.get("catalog_health") if isinstance(race.get("catalog_health"), dict) else {}
        candidates = race.get("candidates") if isinstance(race.get("candidates"), list) else []
        candidate_count = int(health.get("candidate_count") or race.get("candidate_count") or len(candidates))
        missing_images = int(
            health.get("missing_image_count") if health.get("missing_image_count") is not None else _missing_image_count(race)
        )
        forecast = race.get("forecast") if isinstance(race.get("forecast"), dict) else {}
        rating = str(forecast.get("rating") or "").lower()
        competitive = rating in competitive_ratings
        state_haystack = " ".join(
            [
                str(race.get("state") or ""),
                str(race.get("jurisdiction") or ""),
                str(race.get("race_id") or race.get("id") or ""),
            ]
        ).lower()
        office_haystack = " ".join(
            [
                str(race.get("office") or ""),
                str(race.get("title") or ""),
                str(race.get("race_id") or race.get("id") or ""),
            ]
        ).lower()

        if state_query and state_query not in state_haystack:
            continue
        if office_query and office_query not in office_haystack:
            continue
        if publication == "published" and not published:
            continue
        if publication == "unpublished" and published:
            continue
        if research_tier != "all" and tier != research_tier:
            continue
        if missing_images_only and missing_images == 0:
            continue
        if competitive_only and not competitive:
            continue

        priority_score = 0
        reasons: List[str] = []
        if tier == "discovery_only":
            priority_score += 4
            reasons.append("discovery_only")
        elif tier == "partial_research":
            priority_score += 5
            reasons.append("partial_research")
        elif tier == "full_unreviewed":
            priority_score += 3
            reasons.append("needs_review")
        elif tier == "empty":
            priority_score += 6
            reasons.append("missing_roster")
        elif tier == "graded_low":
            priority_score += 3
            reasons.append("low_grade")
        if competitive:
            priority_score += 3
            reasons.append("competitive")
        if missing_images:
            priority_score += min(3, missing_images)
            reasons.append("missing_images")
        if not forecast:
            priority_score += 3
            reasons.append("missing_forecast")
        freshness = str(race.get("freshness") or "").lower()
        if freshness == "old":
            priority_score += 3
            reasons.append("old")
        elif freshness == "stale":
            priority_score += 2
            reasons.append("stale")
        asset_audit = race.get("asset_audit") if isinstance(race.get("asset_audit"), dict) else {}
        if int(asset_audit.get("broken_count") or 0):
            priority_score += min(3, int(asset_audit["broken_count"]))
            reasons.append("broken_assets")
        if int(asset_audit.get("invalid_image_count") or 0) or int(asset_audit.get("suspicious_image_count") or 0):
            priority_score += 2
            reasons.append("image_quality")

        race_id = str(race.get("race_id") or race.get("id") or "")
        pageviews = pageviews_by_race.get(race_id, 0)
        api_requests = requests_by_race.get(race_id, 0)
        demand = max(pageviews, api_requests)
        if demand >= 1000:
            priority_score += 5
        elif demand >= 100:
            priority_score += 4
        elif demand >= 10:
            priority_score += 3
        elif demand:
            priority_score += 2
        if demand:
            reasons.append("user_demand")

        rows.append(
            {
                "race_id": race_id,
                "title": race.get("title"),
                "state": race.get("state"),
                "office": race.get("office"),
                "status": race.get("status"),
                "published": published,
                "research_tier": tier,
                "quality_grade": race.get("quality_grade"),
                "catalog_health": health or None,
                "freshness": race.get("freshness"),
                "candidate_count": candidate_count,
                "missing_image_count": missing_images,
                "asset_audited_at": race.get("asset_audited_at"),
                "broken_asset_count": asset_audit.get("broken_count"),
                "invalid_image_count": asset_audit.get("invalid_image_count"),
                "suspicious_image_count": asset_audit.get("suspicious_image_count"),
                "forecast_rating": rating or None,
                "competitive": competitive,
                "pageviews": pageviews,
                "api_requests": api_requests,
                "traffic_hours": traffic_hours,
                "updated_utc": race.get("updated_utc"),
                "last_run_status": race.get("last_run_status"),
                "has_unpublished_changes": bool(race.get("has_unpublished_changes")),
                "estimated_previous_run_usd": (race.get("agent_metrics") or {}).get("estimated_usd"),
                "priority_score": priority_score,
                "priority_reasons": reasons,
            }
        )

    rows.sort(
        key=lambda row: (
            -int(row["priority_score"]),
            -int(row["pageviews"]),
            -int(row["api_requests"]),
            str(row["race_id"] or ""),
        )
    )
    offset = max(0, offset)
    limit = max(1, min(limit, 200))
    page = rows[offset : offset + limit]
    return {
        "rows": page,
        "matched": len(rows),
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(page) < len(rows),
        "summary": {
            "validated": sum(row["research_tier"] == "validated" for row in rows),
            "graded_low": sum(row["research_tier"] == "graded_low" for row in rows),
            "discovery_only": sum(row["research_tier"] == "discovery_only" for row in rows),
            "partial_research": sum(row["research_tier"] == "partial_research" for row in rows),
            "full_unreviewed": sum(row["research_tier"] == "full_unreviewed" for row in rows),
            "empty": sum(row["research_tier"] == "empty" for row in rows),
            "competitive": sum(bool(row["competitive"]) for row in rows),
            "with_missing_images": sum(int(row["missing_image_count"]) > 0 for row in rows),
            "traffic_hours": traffic_hours,
            "traffic_configured": bool(traffic.get("configured")),
            "traffic_error": traffic.get("error"),
        },
    }


@mcp.tool(structured_output=False)
async def get_race_record(race_id: str) -> Dict[str, Any]:
    """Fetch one admin race record from races-api."""
    return await _client().get(f"/api/races/{race_id}")


@mcp.tool(structured_output=False)
async def list_draft_races() -> Dict[str, Any]:
    """List draft race summaries."""
    return await _client().get("/api/races/drafts")


@mcp.tool(structured_output=False)
async def list_pipeline_steps() -> Dict[str, Any]:
    """List supported pipeline step IDs and labels."""
    return await _client().get("/steps")


@mcp.tool(structured_output=False)
async def get_race_data(race_id: str, draft: bool = False) -> Dict[str, Any]:
    """Fetch full RaceJSON from published data or drafts."""
    return await _client().get(f"/api/races/{race_id}/data", params={"draft": draft})


def _candidate_names(data: Any) -> List[str]:
    """Extract candidate names from a RaceJSON-shaped payload, tolerating missing data."""
    if not isinstance(data, dict):
        return []
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        return []
    return [c.get("name") for c in candidates if isinstance(c, dict) and c.get("name")]


def _roster_completeness_unproven(data: Any) -> bool:
    """Report whether the run said outright that it could not establish the full field.

    Discovery records ``roster_completeness_unproven`` when no authoritative ballot or
    qualified-candidate list was retrievable. The run is still useful — the candidates
    it did evidence are real — but it has disclaimed knowing who else belongs.
    """
    if not isinstance(data, dict):
        return False
    health = data.get("run_health") if isinstance(data.get("run_health"), dict) else {}
    if "roster_completeness_unproven" in {str(r) for r in health.get("reasons") or []}:
        return True
    roster = data.get("pipeline_state", {}) if isinstance(data.get("pipeline_state"), dict) else {}
    research = roster.get("roster_research") if isinstance(roster.get("roster_research"), dict) else {}
    return research.get("completeness_status") == "unproven"


@mcp.tool(structured_output=False)
async def audit_draft_vs_published(race_ids: List[str]) -> Dict[str, Any]:
    """Compare draft vs. published candidate rosters and validation grade for many races at once.

    For each race ID, fetches the current draft (get_race_data with draft=True) and the
    currently published race (get_published_race), then reports candidate name/count
    differences plus the draft's validation_grade and pipeline_state.complete. Missing
    drafts or missing published races are reported (not raised) so one bad race ID doesn't
    abort the whole batch.

    This single comparison serves two purposes depending on when you call it: run it before
    publish_races on the same race_ids to preview what will change (a "publish plan"), and
    again afterward to confirm the live data matches what was planned (publish verification).
    Replaces hand-rolling this comparison race-by-race and saving the results to a scratch
    JSON file.
    """
    client = _client()
    rows: List[Dict[str, Any]] = []
    for race_id in race_ids:
        try:
            draft = await client.get(f"/api/races/{race_id}/data", params={"draft": True})
        except Exception:
            draft = None
        try:
            published = await client.get(f"/races/{race_id}")
        except Exception:
            published = None

        draft_names = _candidate_names(draft)
        published_names = _candidate_names(published)

        grade = None
        passed = None
        if isinstance(draft, dict):
            validation_grade = draft.get("validation_grade")
            if isinstance(validation_grade, dict):
                grade = validation_grade.get("grade")
                passed = validation_grade.get("passed")

        full = False
        if isinstance(draft, dict):
            pipeline_state = draft.get("pipeline_state")
            if isinstance(pipeline_state, dict):
                full = bool(pipeline_state.get("complete"))

        rows.append(
            {
                "race_id": race_id,
                "draft_exists": draft is not None,
                "published_exists": published is not None,
                "full": full,
                "draft_count": len(draft_names),
                "published_count": len(published_names),
                "draft_names": draft_names,
                "published_names": published_names,
                "names_match": sorted(draft_names) == sorted(published_names),
                "grade": grade,
                "passed": passed,
            }
        )

    mismatched = [row["race_id"] for row in rows if not row["names_match"]]
    return {"rows": rows, "mismatched_race_ids": mismatched, "race_count": len(race_ids)}


@mcp.tool(structured_output=False)
async def plan_repairs(race_ids: List[str]) -> Dict[str, Any]:
    """Return deterministic repair groups and cost ceilings without queueing work.

    repair_groups are returned in the order they must be queued, tagged by
    ``stage``: ``roster`` settles the candidate list first, ``candidate`` groups
    research one candidate each and may run in any order among themselves, and
    ``finalization`` runs the race-wide validation tail once, last. Queue each
    group as its own run and let it finish before starting the next stage.

    The combined recommended_steps and candidate_names fields are summaries and
    are not a safe queue payload. estimated_max_cost_usd is a ceiling, not an
    expectation, unless estimate_kind reports observed calibration.
    """
    return await _client().post("/api/races/repair-plan", json={"race_ids": race_ids})


@mcp.tool(structured_output=False)
async def audit_race_assets(
    race_ids: List[str],
    persist: bool = False,
    max_urls_per_race: int = 100,
) -> Dict[str, Any]:
    """Probe source/photo reachability and image content types for selected races."""
    return await _client().post(
        "/api/races/asset-audit",
        json={
            "race_ids": race_ids,
            "persist": persist,
            "max_urls_per_race": max_urls_per_race,
        },
    )


#: Literal junk a model sometimes leaves behind, matched exactly.
#:
#: Narrower than ``shared.run_health.PLACEHOLDER_JUNK_MARKERS`` on purpose, and
#: the difference is the scan, not the judgement: run_health tests one stance
#: string, while this walks every string in a whole draft. Markers that are junk
#: as a stance but plausible as some other field's value — "none", "na", "test" —
#: would block publication over a legitimate district or party here, so they stay
#: out. Everything below is junk wherever it appears.
_PLACEHOLDER_VALUES = frozenset(
    {
        "DRAFT",
        "TODO",
        "TBD",
        "PLACEHOLDER",
        "WIP",
        "FIXME",
        "XXX",
        "DUMMY",
        "LOREM IPSUM",
    }
)


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().upper() in _PLACEHOLDER_VALUES
    if isinstance(value, list):
        return any(_contains_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_placeholder(item) for item in value.values())
    return False


@mcp.tool(structured_output=False)
async def assess_publish_readiness(race_ids: List[str]) -> Dict[str, Any]:
    """Build a conservative batch publish plan without changing production data.

    Checks draft presence, candidate roster, explicit validation pass, run health,
    pipeline completion, literal placeholder content, and draft-vs-published roster
    changes — including blocking a draft that drops a published candidate without
    being able to evidence the roster it kept. A race is ``ready`` only when it has
    no blockers. Warnings still require human review but do not claim the API would
    reject publication.
    """
    client = _client()
    rows: List[Dict[str, Any]] = []
    for race_id in race_ids:
        try:
            draft = await client.get(f"/api/races/{race_id}/data", params={"draft": True})
        except Exception:
            draft = None
        try:
            published = await client.get(f"/races/{race_id}")
        except Exception:
            published = None

        blockers: List[str] = []
        warnings: List[str] = []
        names = _candidate_names(draft)
        if not isinstance(draft, dict):
            blockers.append("draft_missing")
        else:
            if not names:
                blockers.append("candidate_roster_empty")
            # Mirror the races-api gate (gcs_helpers._assert_publishable_race): a
            # *failed* grade blocks, but an absent one does not. A run that never
            # enabled `review` — discovery/polling/forecast maintenance work — can
            # never produce a grade, so treating absence as a blocker made every
            # such draft look unpublishable when the API would accept it.
            validation = draft.get("validation_grade") if isinstance(draft.get("validation_grade"), dict) else None
            if validation is None:
                warnings.append("validation_absent_unreviewed")
            elif validation.get("passed") is not True:
                blockers.append("validation_not_passed")
            error_flags = [
                flag
                for review in draft.get("reviews") or []
                if isinstance(review, dict)
                for flag in review.get("flags") or []
                if isinstance(flag, dict) and flag.get("severity") == "error"
            ]
            if error_flags:
                blockers.append("unresolved_error_flags")
            health = draft.get("run_health") if isinstance(draft.get("run_health"), dict) else {}
            verdict = str(health.get("status") or health.get("verdict") or "unknown")
            if verdict == "failed":
                blockers.append("run_health_failed")
            elif verdict in {"degraded", "unknown"}:
                warnings.append(f"run_health_{verdict}")
            pipeline_state = draft.get("pipeline_state") if isinstance(draft.get("pipeline_state"), dict) else {}
            if not pipeline_state.get("complete"):
                # The API allows an incomplete pipeline only when nothing but
                # `review` is outstanding; anything else is a hard rejection.
                remaining = {str(step) for step in pipeline_state.get("remaining_steps") or []}
                if remaining - {"review"}:
                    blockers.append("pipeline_incomplete_beyond_review")
                else:
                    warnings.append("pipeline_not_complete")
            if _contains_placeholder(draft):
                blockers.append("literal_placeholder_content")

        published_names = _candidate_names(published)
        if published is None:
            warnings.append("first_publication")
        elif sorted(names) != sorted(published_names):
            warnings.append("candidate_roster_changes")
            # Dropping a published candidate asserts they are not in this contest.
            # A run that reported it could not establish the complete field has
            # disclaimed exactly the knowledge that assertion needs, so let it add
            # candidates but never quietly delete one. fl-house-11-2026 halved its
            # roster to a single candidate on an unproven field and still read ready.
            if set(published_names) - set(names) and _roster_completeness_unproven(draft):
                blockers.append("roster_removal_on_unproven_field")
        rows.append(
            {
                "race_id": race_id,
                "ready": not blockers,
                "blockers": blockers,
                "warnings": warnings,
                "draft_candidates": names,
                "published_candidates": published_names,
                "published_exists": published is not None,
            }
        )
    return {
        "rows": rows,
        "ready_race_ids": [row["race_id"] for row in rows if row["ready"]],
        "blocked_race_ids": [row["race_id"] for row in rows if not row["ready"]],
        "all_ready": all(row["ready"] for row in rows),
        "race_count": len(rows),
    }


@mcp.tool(structured_output=False)
async def queue_races(
    race_ids: List[str],
    cheap_mode: bool | None = True,
    force_fresh: bool | None = None,
    baseline_source: Literal["latest", "published"] | None = None,
    resume_partial: bool | None = None,
    save_artifact: bool | None = None,
    enabled_steps: List[str] | None = None,
    research_model: str | None = None,
    claude_model: str | None = None,
    gemini_model: str | None = None,
    grok_model: str | None = None,
    model_profile: str | None = None,
    model_overrides: Dict[str, str] | None = None,
    review_providers: List[str] | None = None,
    max_candidates: int | None = None,
    candidate_names: List[str] | None = None,
    target_no_info: bool | None = None,
    debug_mode: bool | None = None,
    note: str | None = None,
    goal: str | None = None,
    runner: str | None = "local",
) -> Dict[str, Any]:
    """Queue one or more races for pipeline processing.

    Defaults to the cheap `default` profile, routed to the long-lived local Docker
    worker (runner="local"). Pass runner="cloud_run" to use the one-shot Cloud
    Run Job instead (currently broken: the races-api service account is
    missing run.invoker on pipeline-job-dev, so dispatch 403s as of 2026-07-17).
    The expensive `premium` and `custom` model profiles require explicitly passing
    cheap_mode=False. Set baseline_source="published" for a targeted repair
    that must ignore any existing draft; the default "latest" behavior prefers
    a draft and falls back to published data. Set resume_partial=True only when
    the latest draft is a trusted pipeline checkpoint whose completed work-unit
    markers should be preserved instead of deliberately refreshed.
    """
    options = _pipeline_options(
        cheap_mode=cheap_mode,
        force_fresh=force_fresh,
        baseline_source=baseline_source,
        resume_partial=resume_partial,
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
        debug_mode=debug_mode,
        note=note,
        goal=goal,
        runner=runner,
    )
    return await _client().post("/api/races/queue", json={"race_ids": race_ids, "options": options})


@mcp.tool(structured_output=False)
async def refresh_race_core(
    race_ids: List[str],
    baseline_source: Literal["latest", "published"] = "latest",
    include_images: bool = True,
    include_voter_resources: bool = True,
    cheap_mode: bool = True,
    debug_mode: bool = True,
    save_artifact: bool = True,
    runner: str = "local",
    note: str | None = None,
    goal: str | None = None,
) -> Dict[str, Any]:
    """Queue the standard roster-and-race core refresh workflow.

    This is the preferred MCP operation for correcting a suspect roster without
    hand-editing RaceJSON. Discovery verifies the exact-contest roster and
    refreshes candidate summaries/race metadata; optional images then run before
    polling, forecast, and voter-resource refreshes. Debug evidence and artifacts
    default on so roster decisions remain auditable.
    """
    steps = ["discovery"]
    if include_images:
        steps.append("images")
    steps.extend(["polling", "forecast"])
    if include_voter_resources:
        steps.append("voter_resources")
    result = await queue_races(
        race_ids,
        cheap_mode=cheap_mode,
        force_fresh=False,
        baseline_source=baseline_source,
        save_artifact=save_artifact,
        enabled_steps=steps,
        debug_mode=debug_mode,
        note=note or "Pipeline-driven core refresh: roster, summaries, polling, forecast, and resources.",
        goal=goal
        or (
            "Verify the exact office/district roster from current-cycle evidence, remove wrong-contest contamination, "
            "refresh candidate summaries, then update polling and the evidence-backed forecast."
        ),
        runner=runner,
    )
    return {**result, "mode": "core_refresh", "enabled_steps": steps}


@mcp.tool(structured_output=False)
async def run_race(
    race_id: str,
    cheap_mode: bool | None = True,
    force_fresh: bool | None = None,
    baseline_source: Literal["latest", "published"] | None = None,
    enabled_steps: List[str] | None = None,
    debug_mode: bool | None = None,
    note: str | None = None,
    goal: str | None = None,
    runner: str | None = "local",
) -> Dict[str, Any]:
    """Queue a single race for pipeline processing.

    Defaults to the cheap `default` profile, routed to the long-lived local Docker
    worker (runner="local"). Pass runner="cloud_run" to use the one-shot Cloud
    Run Job instead (currently broken: the races-api service account is
    missing run.invoker on pipeline-job-dev, so dispatch 403s as of 2026-07-17).
    Set baseline_source="published" to ignore an existing draft when performing
    a targeted repair.
    """
    options = _pipeline_options(
        cheap_mode=cheap_mode,
        force_fresh=force_fresh,
        baseline_source=baseline_source,
        enabled_steps=enabled_steps,
        debug_mode=debug_mode,
        note=note,
        goal=goal,
        runner=runner,
    )
    return await _client().post(f"/api/races/{race_id}/run", json=options)


@mcp.tool(structured_output=False)
async def publish_race(race_id: str) -> Dict[str, Any]:
    """Publish one draft only after the conservative readiness check passes."""
    readiness = await assess_publish_readiness([race_id])
    if not readiness.get("all_ready"):
        return {
            "published": [],
            "errors": [{"race_id": race_id, "error": "Publish-readiness blockers remain"}],
            "readiness": readiness,
        }
    result = await _client().post(f"/api/races/{race_id}/publish")
    return {**result, "readiness": readiness}


@mcp.tool(structured_output=False)
async def publish_races(race_ids: List[str]) -> Dict[str, Any]:
    """Publish a batch only when every requested draft passes readiness checks."""
    readiness = await assess_publish_readiness(race_ids)
    if not readiness.get("all_ready"):
        return {
            "published": [],
            "errors": [
                {"race_id": race_id, "error": "Publish-readiness blockers remain"}
                for race_id in readiness.get("blocked_race_ids") or []
            ],
            "readiness": readiness,
        }
    result = await _client().post("/api/races/publish", json={"race_ids": race_ids})
    return {**result, "readiness": readiness}


@mcp.tool(structured_output=False)
async def list_unpublished_drafts() -> List[Dict[str, Any]]:
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


@mcp.tool(structured_output=False)
async def unpublish_race(race_id: str) -> Dict[str, Any]:
    """Remove a race from public published data while keeping its draft."""
    return await _client().post(f"/api/races/{race_id}/unpublish")


@mcp.tool(structured_output=False)
async def recheck_race(race_id: str) -> Dict[str, Any]:
    """Reconcile one race status from storage and Firestore state."""
    return await _client().post(f"/api/races/{race_id}/recheck")


@mcp.tool(structured_output=False)
async def recheck_all_races() -> Dict[str, Any]:
    """Reconcile all race statuses through bounded cursor pages."""
    client = _client()
    cursor: str | None = None
    checked = 0
    updated = 0
    page_count = 0
    while True:
        result = None
        for attempt in range(3):
            try:
                result = await client.request(
                    "POST",
                    "/api/races/recheck",
                    params={"limit": 10, **({"cursor": cursor} if cursor else {})},
                )
                break
            except RuntimeError:
                if attempt == 2:
                    raise
                await asyncio.sleep(3 * (attempt + 1))
        assert result is not None
        page_count += 1
        checked += int(result.get("checked") or 0)
        updated += int(result.get("updated") or 0)
        cursor = result.get("next_cursor")
        if not result.get("has_more") or not cursor:
            break
        if page_count >= 100:
            raise RuntimeError("Catalog recheck exceeded 100 pages; refusing an unbounded loop.")
    return {
        "message": f"Rechecked {checked} races across {page_count} page(s)",
        "checked": checked,
        "updated": updated,
        "page_count": page_count,
    }


_US_STATES: Dict[str, str] = {
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
_STATE_NAME_TO_ABBR: Dict[str, str] = {v.lower(): k for k, v in _US_STATES.items()}


def _normalize_state(query: str) -> Tuple[str, str]:
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


@mcp.tool(structured_output=False)
async def list_races_by_state(state: str, office: str | None = None) -> List[Dict[str, Any]]:
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
        state_matches = race_id.startswith(prefix) or race_state.upper() == abbr or full_name.lower() in jurisdiction.lower()
        office_query = str(office or "").strip().lower()
        office_haystack = " ".join(
            [
                race_id,
                str(race.get("office") or ""),
                str(race.get("title") or ""),
                str(race.get("race_type") or ""),
            ]
        ).lower()
        if state_matches and (not office_query or office_query in office_haystack):
            filtered.append(race)
    return filtered


@mcp.tool(structured_output=False)
async def delete_race(race_id: str) -> Dict[str, Any]:
    """Permanently delete a race record, all GCS drafts/published files, and its Firestore entry.

    This is irreversible. Use unpublish_race instead if you only want to hide a race from public view.
    """
    return await _client().delete(f"/api/races/{race_id}")


@mcp.tool(structured_output=False)
async def delete_draft(race_id: str) -> Dict[str, Any]:
    """Delete only the draft version of a race from GCS, keeping the published page and Firestore record."""
    return await _client().delete(f"/api/races/{race_id}/draft")


@mcp.tool(structured_output=False)
async def sleep(seconds: float) -> Dict[str, Any]:
    """Pause execution for the given number of seconds (max 300).

    Useful for waiting between polling operations, rate-limiting retries, or giving the pipeline
    time to process before checking results.
    """
    import asyncio

    clamped = min(max(0, seconds), 300)
    await asyncio.sleep(clamped)
    return {"slept_seconds": clamped}


@mcp.tool(structured_output=False)
async def cancel_race(race_id: str) -> Dict[str, Any]:
    """Cancel a queued or running race."""
    return await _client().post(f"/api/races/{race_id}/cancel")


@mcp.tool(structured_output=False)
async def get_queue(active_only: bool = False, limit: int = 200) -> Dict[str, Any]:
    """List queue items."""
    return await _client().get("/api/queue", params={"active_only": active_only, "limit": limit})


@mcp.tool(structured_output=False)
async def list_runs(limit: int = 50) -> Dict[str, Any]:
    """List recent pipeline runs."""
    return await _client().get("/runs", params={"limit": limit})


@mcp.tool(structured_output=False)
async def list_active_runs() -> Dict[str, Any]:
    """List currently pending or running pipeline runs."""
    return await _client().get("/runs/active")


@mcp.tool(structured_output=False)
async def get_run(run_id: str) -> Dict[str, Any]:
    """Fetch a pipeline run record."""
    return await _client().get(f"/runs/{run_id}")


@mcp.tool(structured_output=False)
async def get_run_logs(
    run_id: str,
    cursor: str | None = None,
    limit: int = 1000,
    since: int | None = None,
) -> Dict[str, Any]:
    """Fetch a bounded page of logs using the prior response's opaque cursor.

    ``since`` remains available for legacy callers, but cursor polling avoids
    repeatedly reading and billing the complete Firestore log collection.
    """
    params: Dict[str, Any] = {"limit": max(1, min(limit, 5000))}
    if cursor is not None:
        params["cursor"] = cursor
    elif since is not None:
        params["since"] = max(0, since)
    return await _client().get(f"/runs/{run_id}/logs", params=params)


@mcp.tool(structured_output=False)
async def get_run_diagnostics(run_id: str) -> Dict[str, Any]:
    """Return normalized diagnostics and health evidence for one pipeline run."""
    return await _client().get(f"/runs/{run_id}/diagnostics")


@mcp.tool(structured_output=False)
async def list_race_runs(race_id: str) -> Dict[str, Any]:
    """List stored run history for one race."""
    return await _client().get(f"/api/races/{race_id}/runs")


@mcp.tool(structured_output=False)
async def get_race_run(race_id: str, run_id: str) -> Dict[str, Any]:
    """Return one race-scoped run record."""
    return await _client().get(f"/api/races/{race_id}/runs/{run_id}")


@mcp.tool(structured_output=False)
async def list_race_versions(race_id: str) -> Dict[str, Any]:
    """List restorable historical RaceJSON versions for one race."""
    return await _client().get(f"/api/races/{race_id}/versions")


@mcp.tool(structured_output=False)
async def get_race_version(race_id: str, filename: str) -> Dict[str, Any]:
    """Read one historical RaceJSON version without restoring it."""
    return await _client().get(f"/api/races/{race_id}/versions/{filename}")


@mcp.tool(structured_output=False)
async def restore_race_version(race_id: str, filename: str) -> Dict[str, Any]:
    """Restore one historical version as the current draft. This mutates draft state."""
    return await _client().post(f"/api/races/{race_id}/versions/{filename}/restore")


@mcp.tool(structured_output=False)
async def cancel_or_delete_run(run_id: str) -> Dict[str, Any]:
    """Cancel an active run or delete a finished run record."""
    return await _client().delete(f"/runs/{run_id}")


@mcp.tool(structured_output=False)
async def get_pipeline_metrics(limit: int = 50) -> Dict[str, Any]:
    """Return recent pipeline cost/token records."""
    return await _client().get("/pipeline/metrics", params={"limit": limit})


@mcp.tool(structured_output=False)
async def get_pipeline_metrics_summary() -> Dict[str, Any]:
    """Return aggregate pipeline cost stats."""
    return await _client().get("/pipeline/metrics/summary")


@mcp.tool(structured_output=False)
async def get_gcp_pipeline_costs(days: int = 30) -> Dict[str, Any]:
    """Return infrastructure-side GCP pipeline costs for the requested lookback."""
    return await _client().get("/pipeline/gcp-costs", params={"days": days})


@mcp.tool(structured_output=False)
async def summarize_run_costs(run_ids: List[str]) -> Dict[str, Any]:
    """Aggregate cost, token, and status data across many pipeline run IDs in one call.

    Prefers normalized provider-backed pipeline metric records, then falls back
    to raw run fields or nested payload.agent_metrics estimates. Returns one row
    per run plus rolled-up status counts, failed/active IDs, and batch totals.

    Useful for auditing a batch of pipeline runs (e.g. tracking progress and spend across a
    multi-race repair effort) without manually calling get_run once per run and hand-
    aggregating the JSON into a scratch file. A run ID that no longer exists is reported
    with status "missing" rather than raising, so one bad ID doesn't abort the whole batch.
    """
    client = _client()
    rows: List[Dict[str, Any]] = []
    status_counts: Dict[str, int] = {}
    total_cost = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    metric_records: Dict[str, Dict[str, Any]] = {}
    try:
        metrics_response = await client.get("/pipeline/metrics", params={"limit": 500})
        if isinstance(metrics_response, dict):
            metric_records = {
                str(record.get("run_id")): record
                for record in metrics_response.get("records", [])
                if isinstance(record, dict) and record.get("run_id")
            }
    except Exception:
        metric_records = {}

    for run_id in run_ids:
        try:
            raw = await client.get(f"/runs/{run_id}")
        except Exception:
            raw = None

        if not isinstance(raw, dict):
            rows.append({"run_id": run_id, "status": "missing"})
            status_counts["missing"] = status_counts.get("missing", 0) + 1
            continue

        metric = metric_records.get(run_id, {})
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
        agent_metrics = raw.get("agent_metrics") if isinstance(raw.get("agent_metrics"), dict) else {}
        if not agent_metrics and isinstance(payload.get("agent_metrics"), dict):
            agent_metrics = payload["agent_metrics"]

        status = raw.get("status") or "unknown"
        race_id = raw.get("race_id") or payload.get("race_id") or metric.get("race_id") or ""

        model_breakdown = metric.get("model_breakdown")
        if not isinstance(model_breakdown, dict):
            model_breakdown = raw.get("model_breakdown")
        if not isinstance(model_breakdown, dict):
            model_breakdown = agent_metrics.get("model_breakdown")
        if not isinstance(model_breakdown, dict):
            model_breakdown = {}

        exact_cost = metric.get("cost_usd")
        if exact_cost is None:
            exact_cost = raw.get("cost_usd")
        if exact_cost is None:
            exact_cost = agent_metrics.get("cost_usd")
        cost_raw = exact_cost
        if cost_raw is None:
            cost_raw = metric.get("estimated_usd")
        if cost_raw is None:
            cost_raw = raw.get("estimated_usd")
        if cost_raw is None:
            cost_raw = agent_metrics.get("estimated_usd")
        try:
            cost = float(cost_raw) if cost_raw is not None else 0.0
        except (TypeError, ValueError):
            cost = 0.0

        prompt_raw = metric.get("prompt_tokens")
        if prompt_raw is None:
            prompt_raw = raw.get("prompt_tokens")
        if prompt_raw is None:
            prompt_raw = agent_metrics.get("prompt_tokens")
        completion_raw = metric.get("completion_tokens")
        if completion_raw is None:
            completion_raw = raw.get("completion_tokens")
        if completion_raw is None:
            completion_raw = agent_metrics.get("completion_tokens")
        try:
            prompt_tokens = int(prompt_raw) if prompt_raw is not None else 0
        except (TypeError, ValueError):
            prompt_tokens = 0
        try:
            completion_tokens = int(completion_raw) if completion_raw is not None else 0
        except (TypeError, ValueError):
            completion_tokens = 0
        if prompt_raw is None or completion_raw is None:
            model_prompt_tokens = 0
            model_completion_tokens = 0
            for model_stats in model_breakdown.values():
                if not isinstance(model_stats, dict):
                    continue
                try:
                    model_prompt_tokens += int(model_stats.get("prompt_tokens") or 0)
                except (TypeError, ValueError):
                    pass
                try:
                    model_completion_tokens += int(model_stats.get("completion_tokens") or 0)
                except (TypeError, ValueError):
                    pass
            if prompt_raw is None:
                prompt_tokens = model_prompt_tokens
            if completion_raw is None:
                completion_tokens = model_completion_tokens

        cost_source = metric.get("cost_source") or raw.get("cost_source") or agent_metrics.get("cost_source")
        if not cost_source:
            cost_source = "provider" if exact_cost is not None else "estimated"

        rows.append(
            {
                "run_id": run_id,
                "race_id": race_id,
                "status": status,
                "cost": cost,
                "has_cost": cost > 0,
                "cost_source": cost_source,
                "model_breakdown": model_breakdown,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "duration_s": metric.get("duration_s") or raw.get("duration_s") or agent_metrics.get("duration_s"),
                "continuation_count": raw.get("continuation_count") or 0,
                "search_calls": metric.get("search_calls")
                or raw.get("search_calls")
                or agent_metrics.get("search_calls")
                or metric.get("serper_calls")
                or raw.get("serper_calls")
                or agent_metrics.get("serper_calls")
                or 0,
                "search_budget_blocked": metric.get("search_budget_blocked")
                or raw.get("search_budget_blocked")
                or agent_metrics.get("search_budget_blocked")
                or 0,
                "token_budget_nudges": metric.get("token_budget_nudges")
                or raw.get("token_budget_nudges")
                or agent_metrics.get("token_budget_nudges")
                or 0,
            }
        )
        status_counts[status] = status_counts.get(status, 0) + 1
        total_cost += cost
        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens

    failed_run_ids = [row["run_id"] for row in rows if row.get("status") == "failed"]
    active_run_ids = [row["run_id"] for row in rows if row.get("status") in ("pending", "running")]

    return {
        "rows": rows,
        "status_counts": status_counts,
        "failed_run_ids": failed_run_ids,
        "active_run_ids": active_run_ids,
        "totals": {
            "cost": total_cost,
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "run_count": len(run_ids),
        },
    }


@mcp.tool(structured_output=False)
async def clear_races_api_cache() -> Dict[str, Any]:
    """Clear the races-api in-memory response cache."""
    return await _client().post("/cache/clear")


@mcp.tool(structured_output=False)
async def get_analytics_overview(hours: int = 24) -> Dict[str, Any]:
    """Fetch request analytics overview for the last N hours."""
    return await _client().get("/analytics/overview", params={"hours": hours})


@mcp.tool(structured_output=False)
async def get_race_analytics(hours: int = 24) -> Dict[str, Any]:
    """Fetch per-race request analytics for the last N hours."""
    return await _client().get("/analytics/races", params={"hours": hours})


@mcp.tool(structured_output=False)
async def get_analytics_timeseries(hours: int = 24, bucket_minutes: int = 60) -> Dict[str, Any]:
    """Fetch bucketed request analytics for charting."""
    return await _client().get("/analytics/timeseries", params={"hours": hours, "bucket": bucket_minutes})


@mcp.tool(structured_output=False)
async def get_traffic_analytics(hours: int = 24) -> Dict[str, Any]:
    """Fetch static-site page views, visits, pages, referrers, countries, and devices."""
    return await _client().get("/analytics/traffic", params={"hours": hours})


@mcp.resource("smartervote://races/summaries")
async def race_summaries_resource():
    """Published race summaries."""
    return await list_race_summaries()


@mcp.resource("smartervote://races/{race_id}")
async def published_race_resource(race_id: str):
    """Published RaceJSON by race ID."""
    return await get_published_race(race_id)


@mcp.prompt()
def review_race_prompt(race_id: str):
    """Prompt for reviewing a SmarterVote race record."""
    return (
        f"Review SmarterVote race `{race_id}`. Load the published race data and, if available, "
        "the draft/admin record. Focus on stale sources, missing candidate data, low-confidence "
        "issue positions, and whether the race should be rerun."
    )


@mcp.tool(structured_output=False)
async def publish_chamber_forecasts() -> Dict[str, Any]:
    """Publish the remotely saved draft chamber forecasts (copy draft -> published)."""
    res = await _client().post("/api/races/chamber_forecasts/publish")
    return {"success": True, "api_response": res}


@mcp.tool(structured_output=False)
async def review_chamber_forecast_drafts() -> Dict[str, Any]:
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


@mcp.tool(structured_output=False)
async def generate_chamber_forecasts(
    model: str = DEFAULT_CHAMBER_FORECAST_MODEL,
    review: bool = False,
    goal: str | None = None,
) -> Dict[str, Any]:
    """Automatically generate chamber-level forecast narratives using an LLM on the remote races-api backend.

    Set ``review=True`` to run a second pass that re-reads each drafted narrative against the same forecast data
    and rewrites claims that contradict it — for instance describing a seat as defended by the party that does not
    hold it. It costs one extra LLM call per chamber and reports what it changed under ``review_corrections``.

    ``goal`` is an optional editorial steer for that pass, e.g. "lead with the tipping-point races". Factual
    corrections always take precedence over it. It requires ``review=True``.
    """
    client = _client()
    payload: Dict[str, Any] = {"model": model, "review": review}
    if goal:
        payload["goal"] = goal
    res = await client.post("/api/races/chamber_forecasts/generate", json=payload)
    return {"success": True, "api_response": res}


def _validate_chamber_forecast_payload(data: Dict[str, Any]) -> Dict[str, Any]:
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

    summary: Dict[str, Any] = {}
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


@mcp.tool(structured_output=False)
async def sync_kalshi_markets(dry_run: bool = False) -> Dict[str, Any]:
    """Synchronize Kalshi election betting market catalog mapping data."""
    from scripts.sync_kalshi_catalog import sync_kalshi_catalog

    return sync_kalshi_catalog(dry_run=dry_run)


@mcp.tool(structured_output=False)
async def verify_live_forecast_page_data() -> Dict[str, Any]:
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
