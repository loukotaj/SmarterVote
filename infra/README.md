# SmarterVote Infrastructure

Terraform configuration for deploying SmarterVote on Google Cloud Platform.

## Current Deployment Model

The production pipeline no longer uses the `pipeline-client` Cloud Run service.

Default production flow:

```text
web admin -> races-api -> Firestore pipeline_queue
  -> Eventarc -> gen2 Cloud Function -> AgentHandler
  -> GCS drafts/ -> admin publish -> GCS races/ (with GCS-side summaries.json updated by races-api)

web admin agent -> races-api -> Firestore admin_agent_tasks
  -> Eventarc -> durable admin-agent Cloud Function
  -> authenticated races-api tools -> messages/tasks persisted in Firestore
```

`enable_pipeline_client` remains available only as a legacy/local debugging option. It should stay `false` for the normal cloud deployment.

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

enable_agent_function       = true
enable_admin_agent_function = true
enable_pipeline_client      = false
```

### 2. Build Cloud Function Source

The deployment workflow builds `infra/functions-agent-source.zip` by copying:

- `functions/agent/main.py`
- `functions/agent/requirements.txt`
- `pipeline_client/`
- `shared/`

Terraform uploads that zip to GCS and deploys the gen2 Cloud Function from it.
It also packages `functions/admin_agent/` into `infra/functions-admin-agent-source.zip`.

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

Queue a race through the admin UI or `races-api`; a new Firestore document in `pipeline_queue/{item_id}` should trigger the agent Cloud Function.

## Components

| Component                  | Default  | Purpose                                                                                                                                                                      |
| -------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| races-api                  | enabled  | Public race API and admin queue/draft/publish API                                                                                                                            |
| Agent Cloud Function       | enabled  | Processes Firestore `pipeline_queue` documents                                                                                                                               |
| Admin Agent Cloud Function | enabled  | Processes durable `admin_agent_tasks` with tool calling and continuation                                                                                                     |
| Eventarc trigger           | enabled  | Invokes the function for each new queue document                                                                                                                             |
| Firestore                  | enabled  | Queue items, run records, logs, race metadata                                                                                                                                |
| GCS bucket                 | enabled  | Drafts, published races (configured with CORS & IAM rules allowing direct public read access to `races/` folder resources for static serving), checkpoints, retired versions |
| Secret Manager             | enabled  | API keys and admin secrets                                                                                                                                                   |
| pipeline-client Cloud Run  | disabled | Legacy/debug-only local pipeline server                                                                                                                                      |

## File Structure

```text
infra/
  main.tf                 Provider config and APIs
  variables.tf            Input variables
  outputs.tf              Terraform outputs
  bucket.tf               GCS storage
  races-api.tf            Cloud Run races API
  agent-function.tf       gen2 Cloud Function + Eventarc trigger
  admin-agent-function.tf durable admin-agent Cloud Function + Eventarc trigger
  monitoring.tf           Firestore and monitoring resources
  secrets.tf              Secret Manager and IAM
  pipeline-client.tf      Legacy optional Cloud Run service
  secrets.tfvars.example  Example local variable file
```

## Concurrency

The Cloud Function uses:

- `max_instance_count = 10`
- `max_instance_request_concurrency = 1`
- Firestore Eventarc trigger on `pipeline_queue/{item_id}`

This means separate queue documents can run in parallel on separate function instances. Each queue item has its own `item_id` and `run_id`, and the function atomically claims only documents whose status is still `pending`.

## Cleanup

```bash
terraform destroy -var-file=secrets.tfvars
```
