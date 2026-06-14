# Maintenance Audit

Last reviewed: 2026-06-12.

## Cleaned

- Production admin routes are canonical under `services/races-api`.
- `pipeline_client/backend/main.py` is local-runner only.
- Admin live updates use REST polling, not persistent WebSocket routes.
- Public sample fallback is disabled outside Vite dev mode.
- Race-level `quality_score` has been removed from product code; migration tooling is in `scripts/remove_quality_score.py`.
- Checked-in stale published race JSON under `services/races-api/data/published/` was removed. Local published data should be pulled or regenerated, not committed.
- OpenRouter migration completed: all LLM runtime calls use `OPENROUTER_API_KEY`; legacy provider keys and Terraform resources were removed.
- GCS Static JSON Hosting completed: Configured CORS and public read access strictly for the GCS bucket `races/` folder. SvelteKit frontend supports static data loading via the new `VITE_PUBLIC_DATA_URL` setting. Publishing/unpublishing from the admin API automatically rebuilds the central `races/summaries.json` index in GCS.
- Race catalog split completed: admin race listings now read Firestore catalog metadata, while public listings use the published GCS `races/summaries.json` index and full GCS race JSON payloads.

## Intentional Compatibility

- `shared.models.LEGACY_ISSUE_NAMES` and `web/src/lib/types.ts` still recognize old issue keys so previously published data can render until those races are rerun.
- `services/races-api/firestore_helpers.py` strips `quality_score` defensively while production data is being cleaned.
- Terraform still contains disabled `enable_pipeline_client` resources for legacy/debug recovery. Normal deployments should keep it `false`; the agent Cloud Function is the production runner.

## Dependency Residuals

- Browserslist/caniuse-lite data was updated during this audit.
- Semver-compatible npm package updates were applied with `npm update`.
- Remaining `npm audit` findings require breaking upgrades or dependency-chain decisions: Svelte 5, Vite 8, Vitest 4, ESLint 10, Prettier 3, and related Svelte tooling. `@tanstack/svelte-table` also reports via the Svelte advisory chain with no direct fix currently available.
- Python requirements are stable enough for the current test suite but are not latest. Major updates to FastAPI/Starlette/Pydantic or the OpenRouter-compatible SDK path should be handled as a separate dependency migration with focused compatibility testing.
