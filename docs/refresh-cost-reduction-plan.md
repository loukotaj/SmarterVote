# Refresh Cost Reduction Plan

Status: implemented; production cost validation remains.

Last reviewed: 2026-08-18.

## Goal

Let a routine `refresh_race_core` cheaply conclude that existing data is still
good instead of forcing every enabled agent phase through its full research
budget. Preserve the core output: roster/metadata, images, polling, forecast,
and voter resources.

## Reviewed design

A short freshness cache was rejected. Age does not prove that a race changed,
and seven days would repeat expensive work throughout the general-election
period. Conversely, blindly trusting even a recent timestamp can miss a
withdrawal or stage transition.

The implemented approach is an evidence-backed fast path:

1. A prior successful roster finalization must exist, including the exact
   candidate names, count, completeness evidence, and contest stage.
2. The stored roster and finalization audit must still match, be proven, and be
   at a known stage. Pre-primary, runoff, general, top-two/top-four,
   uncontested, and special stages are eligible; `unknown` is not.
3. The baseline may be up to 90 days old, configurable with
   `PIPELINE_REFRESH_PROBE_MAX_BASELINE_DAYS` (1–365). This horizon only permits
   a probe; it never skips work by itself.
4. Roster sync and metadata each begin with one current search. If the search
   shows no material change, the agent calls `finish_no_changes` and stops that
   phase. Any uncertainty, changed candidate, stage transition, or relevant new
   development sends it through the normal full workflow.
5. The no-change tool is rejected unless the phase actually performed a search,
   cites a URL returned by that search, and made no edits first. Search is
   not artificially capped: a second search makes the shortcut unavailable and
   commits the agent to the normal workflow.

Accepted no-change exits are logged and recorded in
`pipeline_state.skipped_units`. `refresh_race_core(force_fresh=true)` disables
the fast path by loading no baseline. Manually queued discovery defaults to the
full workflow; only maintenance callers explicitly enable the optimization.

## Existing and expanded early exits

Tool-mode update agents already stop when they make no more tool calls, and the
loop already nudges agents to stop when data is correct. Polling and forecast
also have relatively short synthesis paths. The main blockers were roster sync
and metadata, which required finalization even when nothing changed; the new
no-change tool addresses those two expensive cases without weakening normal
finalization requirements.

The same mechanism can later be enabled for another phase only after defining
what a credible current check means for that data. It should not be turned on
globally: one generic search is not a reliable substitute for a finance filing
check, issue research, or publication review.

## Core refresh scope

The canonical steps remain:

```text
discovery -> images -> polling -> forecast -> voter_resources
```

No other step belongs in every refresh:

- `finance` follows filing events and adds candidate-level cost.
- `refinement` belongs after substantive candidate research changes.
- `issues`, `review`, and `iteration` remain the separately authorized,
  publication-quality research workflow.

Images and voter resources remain optional. Polling and forecast stay paired so
the forecast consumes the latest polling checked by the run.

## Production validation

Run a small set of previously finalized races before any broad batch. Confirm:

- logs show one search followed by `fast no-change exit` on unchanged races
- changed or ambiguous races enter normal discovery rather than calling good
- drafts retain the correct roster and metadata
- search/model calls and `cost_usd` fall materially versus recent core refreshes

Use `get_run_logs`, `get_race_data(draft=true)`, and `summarize_run_costs` for
that comparison. The earlier cost estimates remain hypotheses until this sample
is measured after deployment.
