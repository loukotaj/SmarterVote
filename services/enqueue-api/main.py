"""
FastAPI service for enqueuing race processing jobs.

This service provides a REST API endpoint that accepts race processing
requests and publishes them to Google Cloud Pub/Sub for asynchronous processing.
"""

import base64
import json
import logging
import os
import random
import string
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import pubsub_v1, run_v2
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
CLOUD_RUN_JOB_NAME = os.getenv("CLOUD_RUN_JOB_NAME")
REGION = os.getenv("REGION", "us-central1")

# Initialize Pub/Sub client
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, PUBSUB_TOPIC)

# Initialize Cloud Run client (will be created lazily)
run_client = None


def get_run_client():
    """Get or create the Cloud Run client."""
    global run_client
    if run_client is None:
        run_client = run_v2.JobsClient()
    return run_client


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


class PubSubMessage(BaseModel):
    """Model for Pub/Sub push messages."""

    message: dict
    subscription: Optional[str] = None


async def execute_cloud_run_job(race_id: str, job_id: str) -> bool:
    """
    Execute a Cloud Run job for processing a race.

    Args:
        race_id: The race ID to process
        job_id: The job ID for tracking

    Returns:
        True if job was successfully triggered, False otherwise
    """
    try:
        if not CLOUD_RUN_JOB_NAME:
            logger.error("CLOUD_RUN_JOB_NAME environment variable not set")
            return False

        # Create the job execution request
        run_client = get_run_client()
        job_path = run_client.job_path(PROJECT_ID, REGION, CLOUD_RUN_JOB_NAME)

        # Override the container args to pass the race_id
        execution_request = run_v2.RunJobRequest(
            name=job_path,
            overrides=run_v2.RunJobRequest.Overrides(
                container_overrides=[
                    run_v2.RunJobRequest.Overrides.ContainerOverride(
                        args=[race_id],  # Pass race_id as argument to the pipeline
                        env=[
                            run_v2.EnvVar(name="JOB_ID", value=job_id),
                            run_v2.EnvVar(name="RACE_ID", value=race_id),
                        ],
                    )
                ]
            ),
        )

        # Execute the job
        operation = run_client.run_job(request=execution_request)
        logger.info(f"Started Cloud Run job execution for race {race_id}, job {job_id}")
        logger.info(f"Operation name: {operation.name}")

        return True

    except Exception as e:
        logger.error(f"Failed to execute Cloud Run job for race {race_id}: {e}")
        return False


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
async def process_race(background_tasks: BackgroundTasks, request: ProcessRaceRequest = Body(...)):
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
        raise HTTPException(status_code=500, detail=f"Failed to enqueue race processing: {str(e)}")


@app.post("/webhook")
async def pubsub_webhook(request: Request):
    """
    Webhook endpoint for Pub/Sub push messages.

    This endpoint receives messages from the Pub/Sub subscription and triggers
    Cloud Run job execution for race processing.
    """
    try:
        # Parse the Pub/Sub message
        body = await request.body()
        envelope = json.loads(body.decode("utf-8"))

        # Extract the message data
        pubsub_message = envelope.get("message", {})
        if not pubsub_message:
            logger.error("No message found in Pub/Sub envelope")
            raise HTTPException(status_code=400, detail="Invalid Pub/Sub message format")

        # Decode the base64-encoded data
        message_data = pubsub_message.get("data", "")
        if message_data:
            try:
                decoded_data = base64.b64decode(message_data).decode("utf-8")
                job_data = json.loads(decoded_data)
            except Exception as e:
                logger.error(f"Failed to decode message data: {e}")
                raise HTTPException(status_code=400, detail="Failed to decode message data")
        else:
            # If no data, check attributes
            job_data = pubsub_message.get("attributes", {})

        # Extract job details
        race_id = job_data.get("race_id")
        job_id = job_data.get("job_id")

        if not race_id:
            logger.error("No race_id found in Pub/Sub message")
            raise HTTPException(status_code=400, detail="race_id is required")

        if not job_id:
            logger.error("No job_id found in Pub/Sub message")
            raise HTTPException(status_code=400, detail="job_id is required")

        logger.info(f"Received Pub/Sub message for race {race_id}, job {job_id}")

        # Execute the Cloud Run job
        success = await execute_cloud_run_job(race_id, job_id)

        if success:
            logger.info(f"Successfully triggered Cloud Run job for race {race_id}")
            return {"status": "success", "message": f"Job triggered for race {race_id}"}
        else:
            logger.error(f"Failed to trigger Cloud Run job for race {race_id}")
            raise HTTPException(status_code=500, detail="Failed to trigger job execution")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")


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
