# 2026 Midterm Research Plan

Status: active execution. A catalog-wide core refresh is in progress. Production
snapshot: 2026-08-25 CT (2026-08-26 00:48 UTC).

This plan tracks scope, readiness, priority, and budget. It does not authorize
runs, publication, deployment, or catalog deletion. Operational mechanics remain
canonical in [pipeline-operations.md](pipeline-operations.md).

## Objective

- Cover **506 valid national races**: 435 U.S. House, 35 U.S. Senate, and 36
  governor contests.
- Finish the current catalog-wide core refresh without duplicating the other
  agent's work. A race counts as post-event refreshed only when its stored roster
  timestamp follows the applicable primary/open-election event.
- Review the refreshed roster and record the official-result fingerprint before
  treating discovery as complete or spending on issues.
- Complete reviewed issue research first for every `tossup`, `tilt_*`, and
  `lean_*` race; use corroborated demand for later expansion.
- Keep the **$300 forward research envelope** distinct from all-time pipeline
  telemetry and stop between small cohorts to review quality and actual cost.

`refresh_race_core` remains the correct normal post-primary operation. Do not
restart or overlap a race already owned by the current refresh session. The next
batch must be selected from a fresh `get_research_program_status` plus
`list_active_runs` read because the counts below will move while that agent works.

## Scope

The deployed manifest and catalog now reconcile exactly:

- 506 manifest races;
- 506 catalog-present, published races;
- zero orphaned catalog records;
- five known exclusions enforced by the admission guard.

| Excluded race ID | Reason |
| --- | --- |
| `ar-supreme-court-2026` | Judicial contests are outside the federal-and-governor product scope. |
| `nd-senate-2026` | The regular North Dakota seat is Class III. |
| `vt-senate-2026` | The regular Vermont seat is Class III. |
| `ut-governor-2026` | Utah has no regular 2026 governor election. |
| `ut-senate-2026` | The regular Utah seat is Class III. |

The [Senate Class III roster](https://www.senate.gov/senators/Class_III.htm)
and [Utah official filings](https://vote.utah.gov/2026-candidate-filings/)
support those exclusions. Arkansas holds real judicial elections, but the
national product does not claim dependable judicial coverage.

## Current catalog position

The authoritative status view keeps published, draft, and latest-artifact data
separate. Counts in this section use the explicitly labelled **latest** artifact
unless stated otherwise; seven races currently prefer a draft and 499 prefer the
published artifact.

| Latest-artifact measure | Count |
| --- | ---: |
| Candidates / issue slots | 1,527 / 18,324 |
| Terminal / missing issue slots | 4,270 / 14,054 |
| Races still needing some issue work | 419 |
| Competitive races / competitive issue gaps | 85 / 43 |
| Competitive races with complete issue slots | 42 |
| Incomplete stored roster evidence | 46 |
| Passing stored validation | 125 |
| Validated / discovery-only / graded-low | 125 / 376 / 5 |
| Draft-backed / published-backed latest view | 7 / 499 |
| Active runs at snapshot | 0 |

The published-only view is 128 validated and 378 discovery-only races. That
difference is expected while seven drafts exist; do not blend it with the latest
view or treat a draft regression as published state.

Formal lifecycle status is much less complete than artifact freshness:

| Checkpoint/lifecycle measure | Count |
| --- | ---: |
| Result checkpoints | 25 |
| Waiting / stable / manual review / stabilizing | 481 / 15 / 9 / 1 |
| Discovery complete / review required / manual review / stabilizing / waiting event | 1 / 14 / 9 / 1 / 481 |
| Issues complete / manual review / blocked roster | 1 / 9 / 496 |

This is not evidence that 481 races still need a core run. It means the current
refresh has outpaced result-checkpoint entry. Artifact freshness measures the
refresh campaign; checkpoints measure whether a human-reviewed official result
fingerprint has been closed. Both are required before issue research.

## Current core-refresh campaign

The campaign is essentially halfway through:

| Core-refresh measure | Count |
| --- | ---: |
| Distinct races with roster timestamps since Aug. 21 | 257 / 506 (50.8%) |
| Valid post-event refreshed artifacts | 254 / 506 (50.2%) |
| Settled races still lacking this campaign's refresh | 225 |
| Future-event races that must wait and then be refreshed | 27 |
| Recent core run attempts / completed / cancelled | 271 / 270 / 1 |

Three recently touched races do **not** count as final post-event refreshes:
`ma-house-06-2026` precedes the September 1 primary, while
`la-house-03-2026` and `la-house-06-2026` precede Louisiana's November 3 open
election. They remain in their event-date cohorts.

Progress by office:

| Office | Scope | Recently touched | Remaining now | Remaining with event already held |
| --- | ---: | ---: | ---: | ---: |
| U.S. House | 435 | 234 | 201 | 184 |
| U.S. Senate | 35 | 8 | 27 | 23 |
| Governor | 36 | 15 | 21 | 18 |

The 271 recent core attempts cost **$20.75**, or **$0.077/run**. At that
observed rate, the 252 races still needing a valid post-event refresh project to
about **$19.30**; at the $0.10 target, use **$25.20** as the planning case. The
single cancelled attempt was subsequently retried successfully. Treat model
escalations as outliers: several ordinary runs were below $0.10, while individual
escalated runs exceeded $0.30 and one exceeded $1.

## Order for finishing the core refresh

Do not replace the current agent's queue. When it needs the next work, select in
this order and remove anything that has since acquired a current roster timestamp
or active run.

### 1. Settled competitive races still stale

These 17 races have held their event but did not yet have an Aug. 21-or-later
roster timestamp at the snapshot. The order is rating first, then demand, then
API activity. Process in cohorts of at most five:

| Cohort | Race IDs |
| ---: | --- |
| C1 | `ak-governor-2026`, `tx-senate-2026`, `oh-governor-2026`, `nc-house-11-2026`, `va-house-01-2026` |
| C2 | `mi-senate-2026`, `tx-house-15-2026`, `me-senate-2026`, `ky-house-06-2026`, `nv-governor-2026` |
| C3 | `wi-governor-2026`, `az-01-house-2026`, `ia-governor-2026`, `il-house-06-2026`, `wa-house-03-2026` |
| C4 | `nm-house-03-2026`, `wi-house-03-2026` |

`wa-house-03-2026`, `nm-house-03-2026`, and `wi-house-03-2026` also have issue
gaps. The other 14 already have terminal issue slots, but still merit a core pass
because roster, polling, forecast, images, and voter resources can change without
rerunning issue research.

### 2. Settled races with incomplete stored roster evidence

After C1-C4, refresh the remaining evidence-risk races before broad low-risk
coverage. Prioritize statewide and observed demand in this order:

1. `fl-governor-2026`, `ks-senate-2026`, `nc-senate-2026`,
   `fl-senate-2026-special`, `mt-senate-2026`;
2. `nv-house-04-2026`, `ms-senate-2026`, `ct-house-02-2026`,
   `fl-house-21-2026`, `ne-governor-2026`, `nc-house-10-2026`,
   `va-senate-2026`;
3. `ca-house-05-2026`, `tn-senate-2026`, `wi-house-07-2026`,
   `az-house-04-2026`, `oh-house-14-2026`, `ca-house-24-2026`,
   `md-house-02-2026`, `id-house-02-2026`, `sd-senate-2026`,
   `id-senate-2026`, `il-senate-2026`, `ny-house-20-2026`,
   `or-senate-2026`, `nj-house-01-2026`, `ga-house-04-2026`,
   `id-governor-2026`, `co-senate-2026`, `ne-house-03-2026`,
   `wv-senate-2026`.

The especially high-traffic `fl-governor-2026` and `ca-house-05-2026` should
not be deferred merely because their current ratings are not competitive.

### 3. Remaining settled catalog

After competitive and roster-risk work:

1. finish other statewide races, ordered competitive/likely/safe and then demand;
2. finish remaining likely House seats, ordered by demand and oldest roster date;
3. finish safe House seats in state-sized batches, keeping the five-race review
   boundary even if the worker can run more concurrently.

State batching is efficient, but it is only the final tie-breaker. Do not let an
alphabetical sweep push a statewide, high-demand, or roster-risk race behind a
healthy safe seat.

### 4. Hold future-event cohorts

These dates trigger official-result checks, not automatic runs:

| Event | Races | Action |
| --- | ---: | --- |
| Massachusetts primary, Sep. 1 | 11 | Two stable checks, then governor, Senate, and House core refreshes. |
| New Hampshire primary, Sep. 8 | 4 | Hold all four; `nh-governor-2026` and `nh-house-02-2026` also have competitive issue gaps. |
| Rhode Island primary, Sep. 9 | 4 | Resolve `ri-governor-2026` roster evidence before issues. |
| Delaware primary, Sep. 15 | 2 | Refresh House and Senate after stability. |
| Louisiana open election, Nov. 3 | 6 | Refresh after the open election and again after any applicable runoff; do not treat August touches as final. |

The exact race IDs and dates are canonical in `get_research_manifest`. Verify
results against the relevant state authority; the manifest schedule source alone
does not prove the advancing roster.

## Order for reviewed issue research

Do not mix issue runs into the catalog-wide core campaign. First finish and
inspect the applicable core output, record the stable official-result checkpoint,
and mark its fingerprint reviewed. Then run the combined reviewed workflow from
[pipeline-operations.md](pipeline-operations.md); never queue `issues` alone.

The latest audit has **43 competitive issue-gap races**: six tossups, five tilts,
and 32 leans. The deterministic repair ceiling is $119.23, but it is intentionally
conservative and is not expected spend. Across the latest 40 reviewed-issue
attempts, 34 completed, two failed, and four were cancelled. Completed runs had
a $0.52 median and $0.72 average, with a $4.14 maximum. A 43-race scenario is
therefore about **$22.45 at the median** or **$30.89 at the mean**; retain the
existing **$50 competitive-issues cap** because field size and escalations vary.

Queue in this order, at most five races per review boundary:

| Issue cohort | Race IDs |
| ---: | --- |
| I1 | `fl-house-25-2026`, `co-house-08-2026`, `mi-house-10-2026`, `tx-house-35-2026`, `tx-house-34-2026` |
| I2 | `ca-house-06-2026`, `mi-07-house-2026`, `tx-house-23-2026`, `nj-house-02-2026`, `pa-house-01-2026` |
| I3 | `sc-house-01-2026`, `mi-house-11-2026`, `oh-house-07-2026`, `ca-house-14-2026`, `ak-house-2026` |
| I4 | `mo-house-05-2026`, `mo-house-04-2026`, `oh-house-09-2026`, `wi-house-01-2026`, `pa-house-10-2026` |
| I5 | `az-house-02-2026`, `fl-house-27-2026`, `nh-governor-2026`*, `nj-house-07-2026`, `nv-house-02-2026` |
| I6 | `ny-house-01-2026`, `pa-house-07-2026`, `ne-senate-2026`, `az-06-house-2026`, `ia-house-02-2026` |
| I7 | `md-house-06-2026`, `or-house-04-2026`, `wa-house-03-2026`, `co-house-03-2026`, `in-house-05-2026` |
| I8 | `nm-house-03-2026`, `ny-house-17-2026`, `va-house-05-2026`, `wi-house-03-2026`, `ga-house-02-2026` |
| I9 | `nh-house-02-2026`*, `ny-house-21-2026`, `oh-house-10-2026` |

\* Hold New Hampshire until its September 8 result is stable. When a race is
blocked or already complete at execution time, skip it and preserve the order of
the remaining races; do not promote safe races merely to fill a batch.

After I1-I9, the demand-led likely-race order begins with
`mo-house-06-2026`, `nh-senate-2026`, `fl-house-06-2026`,
`fl-house-16-2026`, `mo-house-02-2026`, `mi-house-03-2026`,
`fl-house-09-2026`, and `wa-house-08-2026`. Re-run the audit before authorizing
that expansion because ratings, traffic, and issue gaps can change.

## Stable-result, quality, and spend gates

Discovery is reviewable only when an official exact-contest source shows every
advancing candidate, unresolved counts or runoffs cannot change the field, and
the roster is unchanged across two checks at least six hours apart. Persist the
URL, times, normalized names, event/date fingerprint, and operator. A changed
fingerprint or degraded run goes to manual review; it does not auto-retry.

For each core cohort:

- confirm no active or duplicate race before queueing;
- inspect roster additions/removals, incumbent flags, parties, and exact-district
  evidence;
- reject name-collision, shared-file, product, group, historical, or otherwise
  unverified candidate images; a null image is preferable to a false identity;
- confirm polls name at least two final-roster candidates in the general-election
  matchup and that forecast lineage remains complete;
- use `get_race_data(draft=true)` and run diagnostics before publication;
- publish only through the readiness gate and only with explicit authorization.

For reviewed issue cohorts, additionally require `validation_grade.passed`, no
literal placeholder text, and populated finance/voting fields where applicable.
A completed pipeline flag alone is insufficient.

Cost controls:

- Core target: at or below $0.10/race; inspect above $0.15 and stop the cohort if
  any run exceeds $0.25 without an understood escalation.
- Reviewed issues: plan at the observed $0.72 average, inspect above $0.75, and
  stop/degrade at $1.25 unless explicitly overridden.
- Count failed and cancelled spend. Classify workflow from `enabled_steps`, not
  `cheap_mode`.

| Forward envelope | Cap |
| --- | ---: |
| Remaining post-event discovery/core | $30 |
| Competitive reviewed issues | $50 |
| Corrections/reviewed retries | $35 |
| Demand-led expansion | $40 |
| Uncommitted reserve | $145 |
| **Total ceiling** | **$300** |

The cost service currently reports **$262.20 all-time** and **$151.89 in the
last 30 days**. Those figures include historical work and are not the balance of
this forward envelope. Campaign-attributable core spend since Aug. 21 is $20.75.
Until program-filtered cost reporting exists, retain the run IDs for every
cohort and use `summarize_run_costs`; do not infer remaining budget by subtracting
all-time telemetry from $300.

## Implemented controls and remaining gaps

The plan's former platform prerequisites are now deployed:

- the committed 506-race manifest and five known exclusions;
- queue/direct-run/publish admission enforcement with sourced overrides;
- result checkpoints and six-hour stable-result validation;
- provenance-separated `get_research_program_status` with manifest-wide counts;
- MCP manifest, status, checkpoint, audit, repair-plan, and canonical core-refresh
  tools;
- the admin **2026 Research** tab and checkpoint editor.

The remaining work is operational first, then product refinement:

1. Backfill result checkpoints as current core outputs are reviewed. This is the
   immediate bottleneck: only 25 of 506 races have checkpoints.
2. Add cohort/program-filtered spend to status. The current workflow totals are
   all-time and cannot enforce the forward $300 envelope by themselves.
3. Add explicit envelope/cohort stop controls and outlier alerts to the admin
   cost surface.
4. Keep Cloudflare, search, and API demand separate; current Cloudflare traffic
   remains approximately one page per visit and should not be the sole spending
   signal.

Latest 30-day Cloudflare traffic is 23,770 pageviews. The forecast page leads
with 4,340; race demand is led by `fl-governor-2026` (1,550 pageviews),
`fl-house-25-2026` (580), and `ca-house-05-2026` (race and candidate pages
combined exceed 1,000). Traffic changes tie-breaking; it never overrides an
unsettled event, suspect roster, or failed quality gate.

The program is complete when all 506 manifest races have a disposition, every
applicable race has reviewed discovery matching its stable result fingerprint,
every then-current competitive race has reviewed complete issues, exceptions are
resolved or explicitly accepted, and attributable forward-program spend is at or
below $300.
