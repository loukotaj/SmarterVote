# SmarterVote Deployment Guide

This guide covers the current deployment path for infrastructure, backend services, the pipeline Cloud Run Job, and the static web frontend.

## Deployment Model

Production uses a serialized release chain after `CI - Quality Gates` passes on `main`:

- CI builds and scans immutable `races-api` and `pipeline-worker` container artifacts.
- `.github/workflows/terraform-deploy.yaml` promotes those exact images, syncs secrets, runs Terraform, and verifies `/health` plus `/health/ready`.
- `.github/workflows/cloudflare-deploy.yaml` starts only after the automatic infrastructure deployment succeeds, pulls published static JSON from GCS, builds the SvelteKit static site with a release-specific asset namespace and a real `404.html`, deploys to Cloudflare Pages, verifies the public home, elections, and support pages plus the complete JavaScript module graph and missing-module 404 behavior, and optionally submits IndexNow URLs.

Deployments are serialized per environment. Every manual apply, rollback, or web deploy requires a commit SHA with a successful `main` push CI run. GitHub environments named `dev`, `staging`, `prod`, and `production` provide deployment policy boundaries; `production` is the public Cloudflare site.

The normal backend flow is:

```text
web admin -> races-api -> Firestore pipeline_queue
  -> pipeline Cloud Run Job -> shared queue processor -> AgentHandler -> GCS drafts/
  -> admin publish -> GCS races/ + races/summaries.json
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
- `VITE_CLOUDFLARE_WEB_ANALYTICS_TOKEN`
- `CLOUDFLARE_PROJECT_NAME` and `CLOUDFLARE_ACCOUNT_ID` when not using defaults
- `ENVIRONMENT` for the Cloudflare static data bucket, defaulting to `dev`
- `PUBLIC_SITE_URL`, defaulting to `https://smarter.vote`
- `GCP_WORKLOAD_IDENTITY_PROVIDER` and `GCP_DEPLOY_SERVICE_ACCOUNT` for keyless GitHub OIDC authentication

`VITE_PUBLIC_DATA_URL` is optional and normally unset. Configure it only when published files are hosted on a
separate public static origin; the current shared GCS bucket also contains private drafts.

Repository secrets:

- `GCP_SA_KEY` only during the OIDC migration; remove it after workload identity is verified
- `OPENROUTER_API_KEY`
- `SERPER_API_KEY`
- `SEARLO_API_KEY` (fallback used only after Serper reports exhausted credits)
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

The script requires `gh` authentication and passes the current full commit SHA to `terraform-deploy.yaml`. The workflow rejects the request unless that SHA has a successful `main` push CI run. On `main`, successful CI automatically applies to the default `dev` environment.

Manual Terraform remains available for local validation or emergency work:

```bash
cd infra
terraform init
terraform plan -var-file=secrets.tfvars
terraform apply -var-file=secrets.tfvars
```

Before manual apply, push the matching `races-api` and `pipeline-worker` image tags, or use GitHub Actions.

## Deploy Web

Cloudflare Pages deploys from `.github/workflows/cloudflare-deploy.yaml` after the corresponding automatic infrastructure deploy succeeds. Manual dispatch requires a verified `deploy_sha`.

The workflow:

1. Authenticates to GCP.
2. Copies `gs://<project>-sv-data-<env>/races/*.json` into `web/static/`.
3. Generates the sitemap from the copied published index and runs the static SvelteKit build.
4. Deploys `web/build` with Wrangler.
5. Submits IndexNow URLs if `INDEXNOW_KEY` is configured.

### Canonical hostname

Cloudflare permanently redirects `www.smarter.vote` to the canonical apex host
with the active zone-level Single Redirect named `Redirect www.smarter.vote to
smarter.vote`. A Pages `_redirects` file cannot match or replace a hostname. The
rule uses Cloudflare's `Redirect from WWW to root` template with:

- Request URL wildcard: `https://www.*`
- Target URL wildcard replacement: `https://${1}`
- Status: `301`
- Query-string preservation enabled

Keep `www.smarter.vote` attached to the Pages project so Cloudflare can serve
the certificate and apply the redirect. Verify both path and query preservation
after changing the rule:

```bash
curl -I "https://www.smarter.vote/races/ga-governor-2026/?ref=verify"
```

The response must be `301` with its `Location` header set to
`https://smarter.vote/races/ga-governor-2026/?ref=verify`.

Candidate retirement redirects are intentionally explicit in
`web/static/_redirects`. Add a candidate-to-candidate redirect only for an
unambiguous slug correction; otherwise point the retired URL to its own race
overview. Include both slash forms to avoid an extra canonicalization hop.

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

Trigger a verified release rollback:

```powershell
.\scripts\deploy.ps1 -Environment dev -Action rollback
```

For an explicit rollback target:

```powershell
.\scripts\rollback.ps1 -Environment prod
.\scripts\rollback.ps1 -Environment prod -ToCommit abc123f
```

Production rollback requires typing `ROLLBACK-PROD`. The script resolves the target commit, verifies it exists, and dispatches `action=rollback` with that SHA. The workflow requires a successful historical `main` CI run, checks out the exact release, applies its Terraform configuration and application version, then verifies API health.

## State And Artifacts

- Terraform remote state is stored in `gs://smartervote-terraform-state`.
- The deploy workflow creates the state bucket if needed and enables versioning.
- Redacted text plan artifacts are uploaded for `plan` actions; machine-readable plan JSON and Terraform state are never uploaded because they can contain secrets.
- Remote state bucket versioning is the state recovery mechanism.
- Generated Terraform plans, state files, and `secrets.tfvars` must not be committed; CI rejects tracked copies.

## Related Documentation

- [Architecture Overview](architecture.md)
- [Local Development](local-development.md)
- [Infrastructure README](../infra/README.md)
- [IndexNow](indexnow.md)
