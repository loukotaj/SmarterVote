# SmarterVote Infrastructure

Terraform configuration for deploying SmarterVote on Google Cloud Platform.

## Current Deployment Model

Production race research uses one-shot Cloud Run Jobs. The removed `pipeline-client` service and the deadline-bound race Cloud Function are not part of the deployed path.

Default production flow:

```text
web admin -> races-api -> Firestore pipeline_queue
  -> Cloud Run Job execution -> shared queue processor -> AgentHandler
  -> GCS drafts/ -> admin publish -> GCS races/ (with GCS-side summaries.json updated by races-api)

web admin agent -> races-api -> Firestore admin_agent_tasks
  -> Eventarc -> durable admin-agent Cloud Function
  -> authenticated races-api tools -> messages/tasks persisted in Firestore
```

The local Docker worker remains permanently supported and claims only queue items explicitly tagged `runner=local`.

## Quick Start

### 1. Configure

```bash
cp secrets.tfvars.example secrets.tfvars
```

Edit `secrets.tfvars`:

```hcl
project_id = "your-gcp-project-id"
region     = "us-central1"

openrouter_api_key = "sk-or-your-openrouter-key"
serper_api_key     = "your-serper-key"
searlo_api_key     = "your-searlo-key"
admin_api_key      = "long-random-admin-key"

enable_admin_agent_function = true
```

### 2. Build Runtime Artifacts

CI builds and scans the `races-api` and `pipeline-worker` containers. The deployment workflow promotes those immutable artifacts by commit SHA. It also packages `functions/admin_agent/` into `infra/functions-admin-agent-source.zip` for the separate durable admin agent.

### 3. Deploy

```bash
terraform init
terraform plan -var-file=secrets.tfvars
terraform apply -var-file=secrets.tfvars
```

### 4. Validate

```bash
curl "$(terraform output -raw races_api_url)/health"
```

Queue a race through the admin UI or `races-api`; the queue document should receive `dispatch_status=submitted`, followed by a Cloud Run Job execution and lease updates.

## Components

| Component                  | Default  | Purpose                                                                                                                                                                      |
| -------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| races-api                  | enabled  | Public race API and admin queue/draft/publish API                                                                                                                            |
| Pipeline Cloud Run Job     | enabled  | One isolated, scale-to-zero execution per queued race                                                                                                                        |
| Admin Agent Cloud Function | enabled  | Processes durable `admin_agent_tasks` with tool calling and continuation                                                                                                     |
| Firestore                  | enabled  | Queue items, run records, logs, race metadata                                                                                                                                |
| GCS bucket                 | enabled  | Private drafts, published build inputs, checkpoints, and retired versions; the web deployment copies published JSON into Cloudflare Pages                            |
| Secret Manager             | enabled  | API keys and admin secrets                                                                                                                                                   |
| Local Docker worker        | manual   | Permanent workstation runner for queue items tagged `runner=local`                                                                                                           |

## Monitoring / Alerts

All alert policies below (`infra/monitoring.tf`) are created only when `alert_email` is set — leave it empty to disable them entirely. Each fires to the single `google_monitoring_notification_channel.email` channel and auto-closes after 7 days if not manually resolved.

| Alert                                | Signal                                                                                                        | Notes                                                                                                    |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `races_api_errors`                    | Cloud Run `run.googleapis.com/request_count` (5xx)                                                              | races-api only                                                                                            |
| `races_api_no_traffic`                | Absence of `run.googleapis.com/request_count`                                                                   | races-api only                                                                                            |
| `races_api_latency`                   | Cloud Run `run.googleapis.com/request_latencies` p95                                                            | races-api only                                                                                            |
| `admin_agent_errors`                  | Cloud Function `cloudfunctions.googleapis.com/function/execution_count` (`status != "ok"`)                      | Also requires `enable_admin_agent_function = true`                                                        |
| `admin_agent_execution_failures`      | Same metric, `status` = `crash` or `timeout`                                                                     | Hard infra failures, not just agent-reported errors; also requires `enable_admin_agent_function = true`   |
| `pipeline_job_failures`               | Cloud Run Job `run.googleapis.com/job/completed_task_attempt_count` (`result = "failed"`)                       | Only the one-shot `runner="cloud_run"` path — does not cover the local worker                             |
| `queue_backlog_elevated`              | Log-based metric `pipeline_queue_pending_depth`, parsed from a `pipeline_queue_depth pending=N running=M` line races-api logs on every `GET /api/queue` | A `google_cloud_scheduler_job` polls that endpoint every 5 minutes so the signal keeps flowing even when no admin has the dashboard open; requires `admin_api_key` to be set (used as the scheduler's `X-Admin-Key` auth) |
| `local_worker_stale`                  | Log-based metric `pipeline_worker_heartbeat`, parsed from a heartbeat log line the long-lived local Docker worker (`pipeline_client/worker.py`) writes directly to Cloud Logging every `WORKER_HEARTBEAT_SECONDS` (default 300s) | Requires the workstation's `gcloud auth application-default login` identity to hold `roles/logging.logWriter` — this is **not** granted by Terraform, since the local worker deliberately has no service account (see `docker-compose.worker.yml`). Proves only that the worker process is up, not that it's running current code. |

Neither `queue_backlog_elevated` nor `local_worker_stale` had a pre-existing signal to alert on — both required adding a small amount of application instrumentation alongside the Terraform (the `pipeline_queue_depth` log line in `services/races-api/routers/queue.py`, and the Cloud Logging heartbeat in `pipeline_client/worker.py`). See the comments above each resource in `monitoring.tf` for the exact log lines they depend on.

## File Structure

```text
infra/
  main.tf                 Provider config and APIs
  variables.tf            Input variables
  outputs.tf              Terraform outputs
  bucket.tf               GCS storage
  races-api.tf            Cloud Run races API
  pipeline-job.tf        one-shot race-processing Cloud Run Job
  admin-agent-function.tf durable admin-agent Cloud Function + Eventarc trigger
  monitoring.tf           Firestore and monitoring resources
  secrets.tf              Secret Manager and IAM
  secrets.tfvars.example  Example local variable file
```

## Concurrency And Recovery

Each queue request starts one single-task job execution. Every task atomically claims its queue item, renews a Firestore lease, and writes terminal state through the shared queue processor. Separate executions can run in parallel; provider quotas and spend remain the practical concurrency limits.

## Cleanup

```bash
terraform destroy -var-file=secrets.tfvars
```
