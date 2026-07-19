# SmarterVote Marketing Design System

This private React package gives Claude a reusable, branded component and token library for creating SmarterVote
marketing material in `claude.ai/design`. Typical outputs include social graphics, campaign explainers, promotional
layouts, and other visual assets that should match the public product without importing the production application.

It is intentionally separate from the SvelteKit frontend. It is not imported by, deployed with, or authoritative for
the production application, and a lack of imports from `web/` is expected rather than dead-code evidence.

The production frontend is the SvelteKit project in `../web/`. When production tokens or shared component styling
change, update this export deliberately and run:

```powershell
npm --prefix design-system ci
npm --prefix design-system run typecheck
npm --prefix design-system run build
```

Design-sync configuration and capture notes live in `../.design-sync/`. Production behavior and component ownership
remain documented in `../docs/architecture.md`.

CI type-checks and builds this package independently. When a production visual change should also appear in marketing
material, deliberately port the relevant tokens or component treatment here; do not make the React package a runtime
dependency of `web/`.
