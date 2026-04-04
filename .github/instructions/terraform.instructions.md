---
applyTo: "infra/**/*.tf"
---

# Terraform Conventions

## Project Context

- GCP project: `smartervote`, environment: `dev`
- State stored remotely in GCS; never run `terraform apply` locally without confirming you're not overwriting shared state
- `enable_pipeline_client` variable controls whether the pipeline-client Cloud Run service is deployed (default: `false`)

## Naming & Structure

- Resources named `{service}-{env}` (e.g., `pipeline-client-dev`, `races-api-dev`)
- Variables declared in `variables.tf`, values in `terraform.tfvars` (never secrets in `.tfvars`)
- Secrets go in `secrets.tfvars` — this file is `.gitignore`d; see `secrets.tfvars.example` for shape
- Outputs in `outputs.tf`; module-specific resources in their own `.tf` file (e.g., `bucket.tf`, `secrets.tf`)

## Cloud Run Rules

- Both services have `deletion_protection = true` — never remove this
- Container images come from Artifact Registry: `us-central1-docker.pkg.dev/smartervote/smartervote-dev/{service}:latest`
- Always set `min_instances = 0` for cost control unless explicitly overriding
- Auth0 env vars (`AUTH0_DOMAIN`, `AUTH0_AUDIENCE`) sourced from Secret Manager — do not hardcode

## Deployment

Every push to `main` auto-deploys via CD workflow. For manual deploys see `docs/deployment-guide.md` and `scripts/deploy_pipeline_client.ps1`.

Validate before committing:
```bash
cd infra && terraform fmt -recursive && terraform validate
```
