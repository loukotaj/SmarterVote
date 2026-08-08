"""Chamber-level forecast draft, generate, and publish endpoints."""

import logging
from typing import Any, Dict

import gcs_helpers
from auth import verify_token
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.model_catalog import DEFAULT_CHAMBER_FORECAST_MODEL

router = APIRouter()

# Re-exported so existing importers keep working. The value itself belongs to
# `shared.model_catalog` — this endpoint, the MCP tool, and the admin UI had
# each grown their own copy of the literal, and two of them had already drifted
# onto a model that was both older and dearer on output.
__all__ = ["DEFAULT_CHAMBER_FORECAST_MODEL", "GenerateForecastsRequest", "router"]


class GenerateForecastsRequest(BaseModel):
    model: str = Field(default=DEFAULT_CHAMBER_FORECAST_MODEL)


@router.get("/api/races/chamber_forecasts/draft", dependencies=[Depends(verify_token)])
async def get_chamber_forecasts_draft_endpoint() -> Dict[str, Any]:
    """Retrieve overall chamber-level forecasts draft from GCS or local file."""
    data = gcs_helpers.load_chamber_forecasts(draft=True)
    if not data:
        raise HTTPException(status_code=404, detail="Chamber forecasts draft not found")
    return data


@router.post("/api/races/chamber_forecasts/generate", dependencies=[Depends(verify_token)])
async def generate_chamber_forecasts_endpoint(
    request: Request, payload: GenerateForecastsRequest = GenerateForecastsRequest()
) -> Dict[str, Any]:
    """Automatically generate chamber-level forecast narratives using an LLM and save them to drafts."""
    from chamber_narratives import generate_chamber_analyses

    from shared.forecast_summary import build_chamber_forecasts

    service = request.app.state.publish_service
    summaries = service.get_race_summaries()

    if not isinstance(summaries, list):
        raise HTTPException(status_code=500, detail=f"Invalid summaries from publish service: {type(summaries)}")

    try:
        analyses = await generate_chamber_analyses(summaries, model=payload.model)
    except Exception as exc:
        logging.error("Error generating chamber forecast analyses using model %s: %s", payload.model, exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"LLM chamber forecast generation failed: {exc}") from exc

    forecast_data = build_chamber_forecasts(
        summaries,
        {chamber: analysis["narrative"] for chamber, analysis in analyses.items()},
        analyses,
    )

    try:
        gcs_helpers.save_chamber_forecasts(forecast_data, draft=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save chamber forecasts draft: {exc}")

    return {
        "message": "Draft chamber forecasts generated successfully",
        "updated_at": forecast_data["updated_at"],
        "model": payload.model,
        "forecast": forecast_data,
    }


@router.post("/api/races/chamber_forecasts/publish", dependencies=[Depends(verify_token)])
async def publish_chamber_forecasts_endpoint(request: Request) -> Dict[str, Any]:
    """Publish the draft chamber-level forecasts (copy draft -> published in GCS)."""
    data = gcs_helpers.load_chamber_forecasts(draft=True)
    if not data:
        raise HTTPException(status_code=404, detail="Chamber forecasts draft not found")

    schema_version = data.get("schema_version")
    if schema_version != "chamber_forecasts.v2":
        raise HTTPException(status_code=400, detail=f"Expected schema_version chamber_forecasts.v2, got {schema_version}")

    chambers = data.get("chambers", {})
    expected_totals = {"house": 435, "senate": 100, "governors": 50}
    required_fields = [
        "seat_distribution",
        "bottom_line",
        "why_party_favored",
        "opposing_party_path",
        "key_uncertainty",
    ]
    for chamber_id, expected_total in expected_totals.items():
        chamber = chambers.get(chamber_id, {})
        if not chamber:
            raise HTTPException(status_code=400, detail=f"{chamber_id} chamber forecast missing")

        projected = chamber.get("projected_seats", {})
        total_projected = sum(projected.values())
        if total_projected != expected_total:
            raise HTTPException(
                status_code=400,
                detail=f"{chamber_id} projected seats must sum to {expected_total}, got {total_projected}",
            )

        for f in required_fields:
            if f not in chamber:
                raise HTTPException(status_code=400, detail=f"{chamber_id} chamber forecast missing required field: {f}")
        if not chamber.get("seat_distribution"):
            raise HTTPException(status_code=400, detail=f"{chamber_id} chamber forecast must include seat_distribution data")

    senate = chambers["senate"]
    if senate.get("vp_tiebreak_party") != "Republican":
        raise HTTPException(status_code=400, detail="Senate chamber forecast missing Republican VP tie-break assumption")
    projected = senate.get("projected_seats", {})
    if projected.get("Democratic") == 50 and projected.get("Republican") == 50:
        if senate.get("control_party") != "Republican":
            raise HTTPException(status_code=400, detail="Senate 50-50 projected split must result in Republican control")

    try:
        gcs_helpers.save_chamber_forecasts(data, draft=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to publish chamber forecasts: {exc}")

    # Clear memory cache on simple publish service
    service = request.app.state.publish_service
    if service:
        service.clear_cache()

    return {"message": "Chamber forecasts published successfully", "updated_at": data.get("updated_at")}
