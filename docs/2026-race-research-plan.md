# 2026 Race Research Operating Plan

Status: active through the 2026 general election.

This is the operating view for completing discovery and issue research across
the covered catalog. It intentionally contains no static race counts, dated
batch ledgers, or estimated spend snapshots: those become wrong as races are
added, primaries settle, and drafts change. Get the current inventory from the
read-only MCP audit before each work session.

This document sets work policy. It does not authorize queueing paid research or
publishing drafts. Queue mechanics, review requirements, and cost accounting
are canonical in [pipeline-operations.md](pipeline-operations.md).

## Outcomes

1. Every covered 2026 race receives **discovery after its relevant primary is
   settled**. Discovery establishes the current contest and nominee roster.
2. Every eligible race receives a complete **issue-research run during
   September**, prioritized by voter demand and competitiveness.
3. At any time, the operator can identify races that are not eligible, ready,
   queued, blocked, or complete without relying on a hand-maintained calendar.

## Compact operating schedule

This is the calendar for operating the backlog, not a second catalog. The live
tracker identifies the exact race IDs in each cohort. Primary dates are checked
against the [NCSL 2026 primary calendar](https://www.ncsl.org/elections-and-campaigns/2026-state-primary-election-dates)
and the [FEC congressional calendar](https://www.fec.gov/resources/cms-content/documents/2026pdates.pdf);
the relevant state election authority controls when a result or field is final.

| Window | Discovery / core-refresh work | Issue work |
| --- | --- | --- |
| Aug. 15–17 | Finish the Hawaii and Aug. 11 cohorts (AL House 1/2/6/7, CT, MN, VT, WI) once results settle. | Only races whose post-primary core refresh has passed review. |
| Aug. 19–31 | Process Alaska, Florida, and Wyoming after the Aug. 18 primary; process Oklahoma only after the Aug. 25 runoff and applicable withdrawal window. | Continue small, demand-ranked cohorts from reviewed races. |
| Sep. 1–18 | Process MA (Sep. 1), NH (Sep. 8), RI (Sep. 9), and DE (Sep. 15) after official results/finalization. | Main September campaign: work through the eligible issue queue in small cohorts. |
| Sep. 21–Oct. 16 | Clear discovery exceptions; do not start issue work for a race with an unresolved field. | Finish competitive gaps first, then likely/open-seat demand. Record named blockers instead of silently skipping them. |
| Oct. 17–Nov. 6 | Read-only catalog check and only material roster corrections. For Louisiana or any special election, use its election authority's current ballot/result schedule rather than a generic primary rule. | No broad new campaign; only voter-demand, roster-change, or correction work. |

Run the tracker after each listed election event and weekly during September.

## The live tracker

At the beginning of each session, run the following read-only tools:

1. `audit_issue_research_readiness(include_rows=true, include_schedule=true,
   traffic_hours=168)` for the catalog inventory, repair workstream, current
   issue gaps, demand, priority queue, and cost ceiling.
2. `list_active_runs()` and `get_queue(active_only=true)` for work already in
   flight. Do not queue a race that appears in either result.
3. `get_race_data(race_id, draft=true)` for any race about to be queued or
   declared complete.

Treat the audit rows as the tracker. Filter or group them using this status
model:

| Status | Meaning | Next action |
| --- | --- | --- |
| `awaiting_primary_result` | The relevant primary has not produced an official settled result. | Wait; record the official result URL when available. |
| `ready_for_discovery` | Official result is verified externally and no run is active. | Queue the post-primary core refresh. |
| `discovery_running` | In `list_active_runs` or active queue. | Monitor; do not duplicate it. |
| `needs_roster_resolution` | Audit workstream is `roster_then_issue_research`, or draft evidence is incomplete. | Run/review discovery before issue work. |
| `ready_for_issues` | Discovery is reviewed, roster is credible, and no run is active. | Rank by demand and queue the combined issue run. |
| `issue_research_running` | In flight. | Monitor and review its draft after completion. |
| `complete` | Discovery or issue run has passed the relevant draft review gate. | Keep in the normal refresh cycle. |
| `manual_review` | Missing artifact, failed grade, contradictory result, or other exception. | Resolve before spending more. |

The tracker needs one human-input field: **official primary result URL and
checked date**. The MCP audit deliberately returns `primary_result_verified:
false`; it has stored race evidence but cannot establish that an election
authority has certified a nominee. Do not turn that field true by inference
from a forecast, media report, or a completed pipeline run.

## Post-primary core refresh: event-driven and cheap

Run discovery as soon as the relevant primary outcome is official enough to
settle the general-election field. For states with runoff, ranked-choice, or
other delayed finalization, wait for the contest that actually determines the
advancing candidate(s). Louisiana-style all-party general elections are an
exception: use the current general-election field rather than inventing a
primary gate.

For the normal post-primary cohort, use the canonical low-cost
`refresh_race_core` tool. It runs discovery in the correct sequence with images,
polling, forecast, and voter resources, so the roster change and voter-facing
maintenance stay together. This is the intended roughly $0.09/race core run.

Use a standalone discovery run only for an urgent roster correction where the
other core data is known-good and refreshing it would be needless work:

```text
queue_races(
  race_ids=[...],
  enabled_steps=["discovery"],
  baseline_source="published"
)
```

Do not use `force_fresh=true` for normal roster settlement; it discards usable
evidence.

After completion, inspect `get_race_data(..., draft=true)`. A finished queue
item is not enough: confirm the exact contest, candidates, candidate summaries,
and roster sources are credible, and confirm `validation_grade.passed` where a
grade is present. Put unresolved evidence, no-candidate results, or
contradictory rosters in `manual_review`.

## September issue-research workflow

Only start issue work after discovery is reviewed. Each session:

1. Start with `audit_issue_research_readiness(..., include_schedule=true)`.
   Its `issue_queue` orders eligible gaps by competitiveness and observed demand
   (page views plus API requests in the selected time window).
2. Remove rows that are awaiting official results, need roster resolution, are
   already active, or have failed draft review.
3. Use `plan_repairs(race_ids)` on the intended small cohort to verify the
   workstream and its maximum estimated cost before spending.
4. Queue the full, reviewed issue bundle—not `issues` alone:

```text
queue_races(
  race_ids=[...],
  enabled_steps=[
    "issues", "finance", "refinement", "polling", "forecast",
    "voter_resources", "review", "iteration"
  ],
  baseline_source="latest"
)
```

Run small sequential cohorts, then review drafts before taking the next cohort.
This keeps September demand-driven while retaining a clear path to full catalog
coverage. Use `baseline_source="published"` only when intentionally discarding
the latest draft.

## MCP data-quality boundaries

The tools are useful, but their sources and limits differ:

| Tool | Reliable for | Do not use it to decide |
| --- | --- | --- |
| `audit_issue_research_readiness` | Stored roster/issue gaps, deterministic repair plans, demand ranking | Whether a primary result is official or a draft is publishable |
| `plan_repairs` | Read-only workstream and bounded cost estimate | Queueing, completion, or publication |
| `list_active_runs` + `get_queue(active_only=true)` | Current pipeline work and duplicate-work avoidance | Draft quality |
| `get_race_data(draft=true)` | The draft actually produced by a run | Election certification |
| `assess_publish_readiness` | A later publication decision | Discovery completion by itself |
| `recheck_all_races` | Catalog reconciliation | A harmless tracker refresh—it mutates catalog status |

Demand data is optional and should never block the roster/issue audit. The
analytics API now returns a neutral `requests` count for the requested `hours`
window; the historical `requests_24h` field remains only as a compatibility
alias. MCP reads the neutral field first and accepts the alias from older API
deployments. Therefore a 168-hour audit ranks on 168-hour API demand, not a
mislabelled 24-hour number.

## Completion rules

Discovery is complete only when the official-result check is recorded, no run
is active, and the reviewed draft has a credible exact-contest roster. Issue
research is complete only when discovery is complete and the combined run's
draft passes review, including actual issue content and populated finance where
applicable. Publication remains a separate, explicit decision.

Re-run the read-only tracker weekly during September and after every primary
result. The resulting rows—not this document—are the current count of work
remaining.
