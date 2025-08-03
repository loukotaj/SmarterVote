"""
FastAPI service for enqueuing race processing jobs.

This service provides a REST API endpoint that accepts race processing
requests and publishes them to Google Cloud Pub/Sub for asynchronous processing.
"""

import os
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import pubsub_v1
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    version="1.0.0"
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
        "timestamp": datetime.utcnow().isoformat()
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
        "components": {
            "pubsub": pubsub_status
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/process", response_model=ProcessRaceResponse)
async def process_race(request: ProcessRaceRequest, background_tasks: BackgroundTasks):
    """
    Enqueue a race for processing.
    
    Args:
        request: Race processing request
        background_tasks: FastAPI background tasks
        
    Returns:
        ProcessRaceResponse with job details
    """
    try:
        # Generate job ID
        job_id = f"job_{request.race_id}_{int(datetime.utcnow().timestamp())}"
        
        # Create message payload
        message_data = {
            "job_id": job_id,
            "race_id": request.race_id,
            "priority": request.priority,
            "retry_count": request.retry_count,
            "metadata": request.metadata or {},
            "enqueued_at": datetime.utcnow().isoformat(),
            "source": "enqueue-api"
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
            enqueued_at=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"Failed to enqueue race {request.race_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enqueue race processing: {str(e)}"
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
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
