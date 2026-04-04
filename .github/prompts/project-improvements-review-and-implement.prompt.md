---
mode: agent
description: Review the full SmarterVote project, propose 5-10 high-impact improvements, and implement approved items.
argument-hint: Optional focus or constraints (for example: cost only, low-risk changes, frontend only, no infra).
---

Run a two-phase improvement workflow for this repository.

## Goal

1. Review the full project and identify improvement opportunities.
2. Propose 5-10 actionable improvements across cost, performance, maintainability, quality, reliability, developer experience, security, and testing.
3. Pause for user approval.
4. Only after approval, implement the approved items end-to-end.

## Phase 1: Review and Proposal (no code changes)

Perform an exhaustive deep review across the codebase (not a quick sample), including:
- `pipeline_client/`
- `services/races-api/`
- `web/`
- `shared/`
- `tests/`
- `infra/`

Produce a ranked proposal list with 5-10 items.

For each item include:
- Title
- Category (cost/performance/maintainability/quality/security/reliability/devex)
- Why it matters
- Expected impact (high/medium/low)
- Estimated implementation effort (small/medium/large)
- Risk level (low/medium/high)
- Validation plan (tests/checks to run)

Then ask the user to approve by item number (for example: "Approve 1, 3, 5").

## Phase 2: Implement Approved Items

After explicit approval:
- Implement all approved items, including medium/high-risk and medium/large efforts when approved.
- Keep changes minimal and targeted.
- Preserve existing architecture and conventions unless the approved item requires change.
- Run relevant validation (tests/lint/build/check) for touched areas.
- Report:
  - What changed
  - Files touched
  - Test/validation results
  - Follow-up recommendations

## Output Format

In Phase 1, provide:

1. Brief review summary
2. Ranked improvements table (5-10 items)
3. Approval request

In Phase 2, provide:

1. Implemented items summary
2. Change log by file
3. Validation results
4. Remaining backlog items

Important: Do not implement any proposed change until the user has approved specific items.
