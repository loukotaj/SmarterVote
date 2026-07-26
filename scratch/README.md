# scratch/

Transient, local-only working files: ad-hoc investigation scripts, one-off analysis
JSON/CSV dumps, log captures, and screenshots. Nothing here is meant to ship or to be
depended on by anything else in the repo.

## Policy

- **Gitignored.** Only this `README.md` and `.gitkeep` are tracked (see the
  `scratch/*` / `!scratch/README.md` / `!scratch/.gitkeep` rules in `.gitignore`).
  Everything else you put here stays local and never gets committed.
- **Disposable.** Treat every file here as regeneratable output you could delete
  today without losing anything load-bearing. Don't rely on scratch/ as storage for
  results you need to keep across sessions — copy anything that matters into a real
  location (docs, a tracked script, an issue/PR description, etc.).
- **Reusable logic belongs in `smartervote_mcp/server.py`.** If you find yourself
  writing the same investigation script twice (draft-vs-published audits, run
  cost/status roll-ups, publish-plan verification, etc.), promote it to a proper MCP
  tool instead of accumulating another one-off script here — see `CLAUDE.md` rule 8
  and the existing tools/tests in `smartervote_mcp/server.py` /
  `tests/test_smartervote_mcp_client.py` for the pattern to follow.
- Genuinely reusable one-off scripts (not MCP-shaped, e.g. browser-automation
  tooling) belong in `scripts/` instead, tracked normally.
