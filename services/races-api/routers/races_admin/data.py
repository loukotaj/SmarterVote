"""Full race JSON (published or draft) read endpoint."""

from typing import Any, Dict

import gcs_helpers
from auth import verify_token
from fastapi import APIRouter, Depends, HTTPException
from request_models import validate_race_id

router = APIRouter()


@router.get("/api/races/{race_id}/data", dependencies=[Depends(verify_token)])
def get_race_data(race_id: str, draft: bool = False) -> Dict[str, Any]:
    """Get full race JSON (published or draft)."""
    validate_race_id(race_id)
    prefix = "drafts" if draft else "races"
    label = "Draft" if draft else "Race"
    data = gcs_helpers._gcs_get_race_json(race_id, prefix)
    if data is None:
        raise HTTPException(status_code=404, detail=f"{label} data not found")
    return data
