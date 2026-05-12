# SmarterVote AI Assistant Instructions

Start every task by reading `.github/copilot-instructions.md`; it is the canonical source for project conventions, build commands, and coding standards.

## Default Workflow

- Check `git status --short` before edits and preserve unrelated user changes.
- Use `rg` / `rg --files` for repo search.
- Keep changes scoped to the requested area and existing architecture.
- Run the narrowest useful validation for touched code before reporting completion.
- Do not publish race data or run deploy/apply actions unless explicitly asked.

## Prompt Shortcuts

- Full CI check: follow `.github/prompts/ci-check.prompt.md`.
- Project improvement review: follow `.github/prompts/project-improvements-review-and-implement.prompt.md`.
- Pipeline agent work: follow `.github/agents/pipeline-researcher.agent.md`.
- Frontend type sync: follow `.github/instructions/frontend-types.instructions.md`.
- Terraform work: follow `.github/instructions/terraform.instructions.md`.

## Validation Defaults

- Python: `PYTHONPATH=. python -m pytest`
- Pipeline: `PYTHONPATH=. python -m pytest tests/test_pipeline.py -v`
- Races API: `cd services/races-api && PYTHONPATH=../.. python -m pytest test_races_api.py -v`
- Frontend: `cd web && npm ci && npm run check && npm run build && npm run test:unit -- --run`
- Terraform: `cd infra && terraform fmt -check -recursive && terraform init -backend=false && terraform validate`

## Detailed Documentation

- **Architecture & endpoints**: `docs/architecture.md`
- **Local development**: `docs/local-development.md`
- **Auth0 setup**: `docs/auth0-configuration.md`
- **Deployment**: `docs/deployment-guide.md`
- **Pipeline modes**: `PIPELINE_MODES.md`
