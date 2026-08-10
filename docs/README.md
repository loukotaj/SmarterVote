# Documentation Map

Last reviewed: 2026-07-26.

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
| Pipeline operations | [pipeline-operations.md](pipeline-operations.md) | Queueing, monitoring, quality review, publication, cost accounting, and recovery |
| Search indexing | [indexnow.md](indexnow.md) | IndexNow setup and deployment integration |
| Marketing design system | [../design-system/README.md](../design-system/README.md) | React export used by Claude to create branded marketing material; not production frontend code |

The current public product surface is documented in [architecture.md](architecture.md#public-web-surface), including the homepage/directory split, national-only launch scope, and informational support and trust pages.

Agent-wide rules live in `../CLAUDE.md`; `../AGENTS.md` is the short entry point. CI commands are defined by `.github/workflows/ci.yaml`, with the runnable agent checklist in `.github/prompts/ci-check.prompt.md`.

## Historical implementation plans

These documents record completed implementation decisions and remaining
operational release checks. They are not general operating instructions.

| Document | Current status |
| --- | --- |
| [pipeline-result-quality-plan.md](pipeline-result-quality-plan.md) | Implementation complete; targeted data-quality QA remains operational work |
| [senate-forecast-page-plan.md](senate-forecast-page-plan.md) | Implementation complete; live publication QA remains an authorized release task |

## Maintenance rules

- Update the closest operational reference when code, configuration, commands, endpoints, or ownership changes.
- Put time-bound work in a plan or handoff with an explicit status and review date.
- Remove completed, superseded, or abandoned plans after any still-current guidance is moved to the appropriate operational reference. Use Git history when old delivery context is needed.
- Link to canonical material instead of copying long command lists or architecture descriptions.
- Never include secrets, private race data, generated Terraform state/plans, or local `.env` values.
