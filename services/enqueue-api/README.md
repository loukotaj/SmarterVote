# SmarterVote Enqueue API

FastAPI service for enqueuing race processing jobs and handling Pub/Sub webhook notifications.

## Overview

This service provides a REST API that:
1. Accepts race processing requests via `/process` endpoint
2. Publishes jobs to Google Cloud Pub/Sub
3. Receives Pub/Sub push notifications via `/webhook` endpoint
4. Triggers Cloud Run job execution for race processing

## Architecture Flow

```
Client → POST /process → Pub/Sub Topic → Pub/Sub Subscription → POST /webhook → Cloud Run Job
```

## API Endpoints

### `GET /`
Health check endpoint that returns service status.

### `GET /health`
Detailed health check that verifies Pub/Sub connectivity.

### `POST /process`
Enqueue a race for processing.

**Request Body:**
```json
{
  "race_id": "mo-senate-2024",
  "priority": 1,
  "retry_count": 0,
  "metadata": {}
}
```

**Response:**
```json
{
  "success": true,
  "message": "Race mo-senate-2024 enqueued for processing",
  "job_id": "job_mo-senate-2024_1723305600000_abc123",
  "race_id": "mo-senate-2024",
  "enqueued_at": "2024-08-10T12:00:00Z"
}
```

### `POST /webhook`
Internal webhook endpoint for Pub/Sub push notifications. This endpoint:
- Receives base64-encoded job data from Pub/Sub
- Extracts race_id and job_id from the message
- Triggers the corresponding Cloud Run job execution

**Expected Pub/Sub Message Format:**
```json
{
  "message": {
    "data": "base64-encoded-job-data",
    "messageId": "message-id",
    "publishTime": "2024-08-10T12:00:00Z"
  },
  "subscription": "projects/project-id/subscriptions/race-jobs-sub"
}
```

### `GET /metrics`
Returns basic service metrics (placeholder for future implementation).

## Environment Variables

- `PROJECT_ID` - Google Cloud project ID
- `PUBSUB_TOPIC` - Pub/Sub topic name for race jobs
- `CLOUD_RUN_JOB_NAME` - Name of the Cloud Run job to execute
- `REGION` - Google Cloud region (default: us-central1)

## Dependencies

- FastAPI for the web framework
- Google Cloud Pub/Sub for message queuing
- Google Cloud Run for job execution
- Pydantic for request/response validation

## Testing

Run tests with:
```bash
python -m pytest test_enqueue_api.py -v
```

Test coverage includes:
- API endpoint functionality
- Pub/Sub message publishing
- Webhook message processing
- Cloud Run job triggering
- Error handling scenarios
