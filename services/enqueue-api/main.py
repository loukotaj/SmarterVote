"""
FastAPI service for enqueuing race processing jobs.

This service provides a REST API endpoint that accepts race processing
requests and publishes them to Google Cloud Pub/Sub for asynchronous processing.
"""

import json
import logging
import os
import random
import string
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import pubsub_v1
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_job_id(race_id: str) -> str:
    """
    Generate a unique job ID using timestamp and random suffix.

    Args:
        race_id: The race ID to include in the job ID

    Returns:
        Unique job ID string
    """
    timestamp = int(datetime.utcnow().timestamp() * 1000)  # millisecond precision
    random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"job_{race_id}_{timestamp}_{random_suffix}"


# Environment variables
PROJECT_ID = os.getenv("PROJECT_ID")
PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC", "race-processing")

# Initialize Pub/Sub client
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, PUBSUB_TOPIC)

# Initialize FastAPI app
app = FastAPI(
    title="SmarterVote Enqueue API",
    description="API for enqueuing electoral race processing jobs",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "smartervote-enqueue-api",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health")
async def health_check():
    """Detailed health check."""
    try:
        # Test Pub/Sub connection
        publisher.get_topic(request={"topic": topic_path})
        pubsub_status = "healthy"
    except Exception as e:
        logger.error(f"Pub/Sub health check failed: {e}")
        pubsub_status = "unhealthy"

    return {
        "service": "smartervote-enqueue-api",
        "status": "healthy" if pubsub_status == "healthy" else "degraded",
        "components": {"pubsub": pubsub_status},
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/process", response_model=ProcessRaceResponse)
async def process_race(
    background_tasks: BackgroundTasks, request: ProcessRaceRequest = Body(...)
):
    """
    Enqueue a race for processing.

    Args:
        request: Race processing request
        background_tasks: FastAPI background tasks

    Returns:
        ProcessRaceResponse with job details
    """
    try:
        # Generate unique job ID
        job_id = generate_job_id(request.race_id)

        # Create message payload
        message_data = {
            "job_id": job_id,
            "race_id": request.race_id,
            "priority": request.priority,
            "retry_count": request.retry_count,
            "metadata": request.metadata or {},
            "enqueued_at": datetime.utcnow().isoformat(),
            "source": "enqueue-api",
        }

        # Publish to Pub/Sub
        message_json = json.dumps(message_data)
        message_bytes = message_json.encode("utf-8")

        future = publisher.publish(topic_path, message_bytes)
        message_id = future.result(timeout=30.0)

        logger.info(f"Published message {message_id} for race {request.race_id}")

        return ProcessRaceResponse(
            success=True,
            message=f"Race {request.race_id} enqueued for processing",
            job_id=job_id,
            race_id=request.race_id,
            enqueued_at=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"Failed to enqueue race {request.race_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to enqueue race processing: {str(e)}"
        )


@app.get("/metrics")
async def get_metrics():
    """Get basic service metrics."""
    # TODO: Implement actual metrics collection
    return {
        "total_jobs_processed": 0,
        "jobs_in_queue": 0,
        "average_processing_time": 0,
        "error_rate": 0,
        "timestamp": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
