# SmarterVote AI Assistant Instructions

See `CLAUDE.md` for the canonical project guide — conventions, validation commands, architecture, and key rules.

## Default Workflow

- Check `git status --short` before edits and preserve unrelated user changes.
- Use `rg` / `rg --files` for repo search.
- Keep changes scoped to the requested area and existing architecture.
- Run the narrowest useful validation for touched code before reporting completion.
- Do not publish race data or run deploy/apply actions unless explicitly asked.
- GCP/deployed is always the source of truth; CI is the validation gate.
- Treat `docs/README.md` as the documentation map. Operational guides describe current behavior; plans and handoffs are historical unless their status says otherwise.
- When behavior, commands, configuration, or ownership changes, update the nearest canonical guide in the same change instead of adding a second source of truth.

## Prompt Shortcuts

- Full CI check: follow `.github/prompts/ci-check.prompt.md`.
- Project improvement review: follow `.github/prompts/project-improvements-review-and-implement.prompt.md`.
- Pipeline agent work: follow `.github/agents/pipeline-researcher.agent.md`.
- Frontend type sync: follow `.github/instructions/frontend-types.instructions.md`.
- Terraform work: follow `.github/instructions/terraform.instructions.md`.
