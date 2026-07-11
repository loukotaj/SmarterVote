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
admin_api_key      = "long-random-admin-key"

enable_admin_agent_function = true
```

### 2. Build Runtime Artifacts

The deployment workflow builds and pushes the `races-api` and `pipeline-worker` containers. It also packages `functions/admin_agent/` into `infra/functions-admin-agent-source.zip` for the separate durable admin agent.

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
| GCS bucket                 | enabled  | Drafts, published races (configured with CORS & IAM rules allowing direct public read access to `races/` folder resources for static serving), checkpoints, retired versions |
| Secret Manager             | enabled  | API keys and admin secrets                                                                                                                                                   |
| Local Docker worker        | manual   | Permanent workstation runner for queue items tagged `runner=local`                                                                                                           |

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
