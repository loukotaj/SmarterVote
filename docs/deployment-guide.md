# SmarterVote Deployment Guide

This guide covers the current deployment path for infrastructure, backend services, the pipeline Cloud Run Job, the admin Cloud Function, and the static web frontend.

## Deployment Model

Production uses two GitHub Actions workflows after `CI - Quality Gates` passes on `main`:

- `.github/workflows/terraform-deploy.yaml` builds the `races-api` and `pipeline-worker` containers, packages the admin-agent Function, syncs secrets, and runs Terraform.
- `.github/workflows/cloudflare-deploy.yaml` pulls published static JSON from GCS, builds the SvelteKit static site, deploys to Cloudflare Pages, and optionally submits IndexNow URLs.

The normal backend flow is:

```text
web admin -> races-api -> Firestore pipeline_queue
  -> pipeline Cloud Run Job -> shared queue processor -> AgentHandler -> GCS drafts/
  -> admin publish -> GCS races/ + races/summaries.json
```

The durable admin agent follows:

```text
web admin agent -> races-api -> Firestore admin_agent_tasks
  -> Eventarc -> functions/admin_agent -> authenticated races-api tools
```

The local Docker worker remains supported for `runner=local`; it is not deployed as an always-on cloud service.

## Required GitHub Configuration

Repository variables:

- `GCP_PROJECT_ID`
- `AUTH0_DOMAIN`
- `AUTH0_AUDIENCE`
- `CLOUDFLARE_ANALYTICS_ACCOUNT_TAG`
- `CLOUDFLARE_ANALYTICS_SITE_TAG`
- `RACES_API_URL` for the frontend build
- `VITE_PUBLIC_DATA_URL` for static GCS race reads
- `VITE_CLOUDFLARE_WEB_ANALYTICS_TOKEN`
- `CLOUDFLARE_PROJECT_NAME` and `CLOUDFLARE_ACCOUNT_ID` when not using defaults
- `ENVIRONMENT` for the Cloudflare static data bucket, defaulting to `dev`

Repository secrets:

- `GCP_SA_KEY`
- `OPENROUTER_API_KEY`
- `SERPER_API_KEY`
- `ADMIN_API_KEY`
- `CLOUDFLARE_ANALYTICS_API_TOKEN`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID` when not configured as a variable
- `INDEXNOW_KEY` if IndexNow submission is enabled

## Deploy Infrastructure

Use the helper script to trigger the Terraform workflow:

```powershell
.\scripts\deploy.ps1 -Environment dev -Action plan
.\scripts\deploy.ps1 -Environment dev -Action apply
```

The script requires `gh` authentication and triggers `terraform-deploy.yaml`. On `main`, a successful CI run also triggers an `apply` to the default `dev` environment.

Manual Terraform remains available for local validation or emergency work:

```bash
cd infra
terraform init
terraform plan -var-file=secrets.tfvars
terraform apply -var-file=secrets.tfvars
```

Before manual apply, push the matching `races-api` and `pipeline-worker` image tags and build `infra/functions-admin-agent-source.zip`, or use GitHub Actions.

## Deploy Web

Cloudflare Pages deploys from `.github/workflows/cloudflare-deploy.yaml` after CI passes on `main`, or by manual dispatch.

The workflow:

1. Authenticates to GCP.
2. Copies `gs://<project>-sv-data-<env>/races/*.json` into `web/static/`.
3. Runs `npm run build:cloudflare`.
4. Deploys `web/build` with Wrangler.
5. Submits IndexNow URLs if `INDEXNOW_KEY` is configured.

## Validate

```powershell
.\scripts\validate-infra.ps1 -Environment dev
```

Useful direct checks:

```bash
curl "$(terraform -chdir=infra output -raw races_api_url)/health"
curl "$(terraform -chdir=infra output -raw races_api_url)/health/ready"
```

For local gates before pushing:

```powershell
.\scripts\run-ci-gates.ps1
```

## Rollback

Trigger a workflow rollback:

```powershell
.\scripts\deploy.ps1 -Environment dev -Action rollback
```

For emergency branch-based rollback:

```powershell
.\scripts\rollback.ps1 -Environment prod
.\scripts\rollback.ps1 -Environment prod -ToCommit abc123f
```

Production rollback requires typing `ROLLBACK-PROD`. The rollback script creates a rollback branch, restores `infra/` from the target commit, commits it, pushes it, and triggers an apply from that branch.

## State And Artifacts

- Terraform remote state is stored in `gs://smartervote-terraform-state`.
- The deploy workflow creates the state bucket if needed and enables versioning.
- Plan artifacts are uploaded for `plan` actions.
- State backup artifacts are uploaded when available.
- Generated Terraform plans, state files, and `secrets.tfvars` must not be committed; CI rejects tracked copies.

## Related Documentation

- [Architecture Overview](architecture.md)
- [Local Development](local-development.md)
- [Infrastructure README](../infra/README.md)
- [IndexNow](indexnow.md)
