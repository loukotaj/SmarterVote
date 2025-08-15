from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProcessRaceRequest(BaseModel):
    """Request model for processing a race."""

    race_id: str
    priority: Optional[int] = 1
    retry_count: Optional[int] = 0
    metadata: Optional[dict] = None


class ProcessRaceResponse(BaseModel):
    """Response model for race processing requests."""

    success: bool
    message: str
    job_id: str
    race_id: str
    enqueued_at: datetime


class PubSubMessage(BaseModel):
    """Model for Pub/Sub push messages."""

    message: dict
    subscription: Optional[str] = None
