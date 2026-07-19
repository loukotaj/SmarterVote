# Documentation Map

Last reviewed: 2026-07-18.

Use this page to decide which documents describe current behavior. Code, deployed GCP resources, and CI remain the final source of truth; documentation should be updated alongside behavior changes.

## Current operational references

| Topic | Document | Authority |
| --- | --- | --- |
| Architecture and ownership | [architecture.md](architecture.md) | Production topology, storage, and API ownership |
| Local setup and commands | [local-development.md](local-development.md) | Developer environment and service startup |
| Deployment | [deployment-guide.md](deployment-guide.md) | GitHub Actions deployment and rollback flow |
| Authentication | [auth0-configuration.md](auth0-configuration.md) | Auth0 and admin-key behavior |
| Infrastructure | [../infra/README.md](../infra/README.md) | Terraform components and defaults |
| Pipeline modes | [../PIPELINE_MODES.md](../PIPELINE_MODES.md) | Local/GCP execution and storage modes |
| Search indexing | [indexnow.md](indexnow.md) | IndexNow setup and deployment integration |

The current public product surface is documented in [architecture.md](architecture.md#public-web-surface), including the homepage/directory split, national-only launch scope, and informational support and trust pages.

Agent-wide rules live in `../CLAUDE.md`; `../AGENTS.md` is the short entry point. CI commands are defined by `.github/workflows/ci.yaml`, with the runnable agent checklist in `.github/prompts/ci-check.prompt.md`.

## Active plans

These documents track unfinished work. They are not general operating instructions and should be removed once their remaining work is delivered or abandoned.

| Document | Status |
| --- | --- |
| [pipeline-result-quality-plan.md](pipeline-result-quality-plan.md) | Active quality-improvement plan; consult its delivered/remaining sections |
| [senate-forecast-page-plan.md](senate-forecast-page-plan.md) | Partially complete product plan |

## Maintenance rules

- Update the closest operational reference when code, configuration, commands, endpoints, or ownership changes.
- Put time-bound work in a plan or handoff with an explicit status and review date.
- Remove completed, superseded, or abandoned plans after any still-current guidance is moved to the appropriate operational reference. Use Git history when old delivery context is needed.
- Link to canonical material instead of copying long command lists or architecture descriptions.
- Never include secrets, private race data, generated Terraform state/plans, or local `.env` values.
