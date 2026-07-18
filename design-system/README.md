# SmarterVote Design Export

This private React package mirrors selected SmarterVote visual components for the design-sync workflow. It is not
imported by, deployed with, or authoritative for the production application.

The production frontend is the SvelteKit project in `../web/`. When production tokens or shared component styling
change, update this export deliberately and run:

```powershell
npm --prefix design-system ci
npm --prefix design-system run typecheck
npm --prefix design-system run build
```

Design-sync configuration and capture notes live in `../.design-sync/`. Production behavior and component ownership
remain documented in `../docs/architecture.md`.
