# 2026 Midterm Research Plan

Status: active planning; paid work is on hold pending credential/payment
readiness and the discovery-cost fix. Last production audit: 2026-08-18.

This plan tracks scope, readiness, priority, and budget. It does not authorize
runs, publication, deployment, or catalog deletion. Operational mechanics remain
canonical in [pipeline-operations.md](pipeline-operations.md).

## Objective

- Cover **507 valid races**: 435 U.S. House, 35 U.S. Senate, 36 governor, and
  the Arkansas Supreme Court contest.
- Give each covered race one reviewed discovery/core refresh after its
  general-election field settles.
- Complete reviewed issue research for every `tossup`, `tilt_*`, and `lean_*`
  race during September; use demand for later expansion.
- Keep most of the initial **$300** uncommitted until two settled-race pilots
  prove cost and quality.

`refresh_race_core` is the correct normal post-primary operation. The missing
controls are upstream: validate the race, prove its result is stable, and allow
only one run per stable-result fingerprint.

## Scope correction

Firestore contains 511 race-like records but is not an election manifest. Four
records are outside valid 2026 scope:

| Race ID | Production state | Disposition |
| --- | --- | --- |
| `nd-senate-2026` | Cancelled; no artifact | Retire; the seat is Class III. |
| `vt-senate-2026` | Cancelled; no artifact | Retire; the seat is Class III. |
| `ut-governor-2026` | Cancelled; no artifact | Retire; no regular 2026 contest. |
| `ut-senate-2026` | **Published** with reviewed issues | Unpublish/retire; the seat is Class III. |

The [Senate Class III roster](https://www.senate.gov/senators/Class_III.htm)
places John Hoeven, Peter Welch, and Mike Lee in terms ending in 2029; the
[Class II roster](https://www.senate.gov/senators/Class_II.htm) is the regular
2026 cycle. [Utah's official filings](https://vote.utah.gov/2026-candidate-filings/)
list no U.S. Senate or governor contest. The three empty records are not missing
research; `ut-senate-2026` is a published data-quality incident.

`ar-supreme-court-2026` is real, published, and validated. “Every race” means
the validated 507-race product scope, not every state/local election nationally.

## Current position

| Valid-scope measure | Count | View |
| --- | ---: | --- |
| Covered and published races | 507 | Reconciled scope |
| Candidates / issue slots | 1,528 / 18,336 | Latest repair artifact |
| Terminal / missing issue slots | 4,334 / 14,002 | Latest repair artifact |
| Races still needing issue work | 416 | Latest repair artifact |
| Competitive / competitive issue gaps | 81 / 44 | Rating + latest repair |
| Incomplete stored roster evidence | 227 | Latest repair artifact |
| Passing stored validation | 115 | Latest repair artifact |
| Validated / discovery-only / partial | 114 / 392 / 1 | Published catalog |
| Active runs / queue | 0 / 0 | Live pipeline state |

Office composition:

| Office | Races | Candidates | Competitive | Published validated |
| --- | ---: | ---: | ---: | ---: |
| U.S. House | 435 | 1,250 | 65 | 63 |
| Governor | 36 | 128 | 10 | 16 |
| U.S. Senate | 35 | 152 | 6 | 34 |
| Arkansas Supreme Court | 1 | 2 | 0 | 1 |

The $1,192.98 all-gap repair ceiling prices broad stored candidate fields. It
is not expected spend. Settle each roster and re-plan before reserving money.

## Demand and cost findings

Traffic is a ranking signal, never a readiness gate or sole reason to spend.

| Signal | Audited result |
| --- | --- |
| Cloudflare, 7 days | 5,659 pageviews; 4,829 mapped to valid races |
| Cloudflare, 30 days | 20,480 pageviews; 15,730 mapped to valid races |
| Bing, Jun. 16-Aug. 17 | 4,104 clicks / 105,730 impressions / 3.88% CTR |
| Google, May 17-Aug. 16 | 134 clicks / 4,022 impressions |

Bing produced 1,126 clicks in the latest seven days, up 13.9% from 989. Its
latest 30 days produced 3,614 clicks versus 485 in the preceding 30 days.
Cloudflare's 30-day response is about 98% desktop, 95% direct, and 1.0 page per
visit, so it may include bots or analytics aggregation. Require another signal
(search landing-page activity, API demand, or competitiveness) before traffic
overrides issue priority.

Latest 500-run/metric join:

| Workflow | Runs | Average | Median | Maximum | Healthy |
| --- | ---: | ---: | ---: | ---: | ---: |
| Standalone discovery | 103 | $0.242 | $0.104 | $2.171 | 49% |
| Discovery with core steps | 173 | $0.112 | $0.075 | $0.722 | 80% |
| Full reviewed issues | 15 | $0.678 | $0.648 | $1.559 | 53% |
| Full reviewed, 2 candidates | 4 | $0.433 | $0.417 | $0.551 | 75% |
| Full reviewed, 3 candidates | 6 | $0.592 | $0.591 | $0.708 | 67% |
| Full reviewed, 4+ candidates | 5 | $0.979 | $0.934 | $1.559 | 20% |

Discovery is not ready for a broad batch. Waiting for narrowed rosters reduces
issue cost and failure risk: the current 44 competitive gaps project to roughly
**$26.40** at a conservative $0.60 two-candidate rate. Partial issue workflows
are not completion evidence because they omit review/iteration.

The cost service reports $108.23 in the last 30 days and $215.53 lifetime, but
its `cheap`/`full` split is model mode, not workflow. GCP infrastructure spend
is unknown because the billing-export dataset is missing/unreadable.

## Priority and schedule

Ready work is ordered by:

1. stable official result;
2. tossup, tilt, then lean;
3. corroborated demand within a rating;
4. lower-cost two-candidate fields when otherwise tied.

The leading seven-day Cloudflare race pages are `fl-governor-2026` (1,057),
`ca-house-05-2026` (387), `fl-house-25-2026` (310), `fl-house-22-2026`
(266), `fl-house-13-2026` (261), `ak-governor-2026` (222), and
`fl-house-07-2026` (206). Florida/Alaska are the first result-check cohort;
`fl-house-13-2026` is the strongest current issue-gap candidate once settled.

Dates trigger checks, not automatic runs:

| Window | Discovery/core | Issues |
| --- | --- | --- |
| Now-Aug. 24 | Hold paid work; verify HI, AL/CT/MN/VT/WI, then AK/FL/WY results. | Select two pilot races only. |
| Aug. 25-31 | Check OK/applicable special runoffs; require credentials, admission guard, and cost fix. | Run the two-race pilot only with approval. |
| Sep. 1-18 | Process MA, NH, RI, and DE after stable results. | Competitive cohorts of at most five. |
| Sep. 19-Oct. 16 | Finish discovery exceptions. | Finish competitive gaps, then corroborated high demand. |
| Oct. 17-Nov. 2 | Material corrections only. | Newly competitive/demanded/corrective only. |
| Nov. 3-Dec. 12 | Handle Louisiana's open election/runoff after the applicable event. | Avoid broad fields unless demand justifies them. |

Verify dates with [NCSL](https://www.ncsl.org/elections-and-campaigns/2026-state-primary-election-dates),
the [FEC calendar](https://www.fec.gov/resources/cms-content/documents/2026pdates.pdf),
and the relevant state authority.

## Stable-result and spend gates

Discovery is ready only when an official exact-contest source shows every
advancing candidate, unresolved counts/runoffs cannot change the field, and the
roster is unchanged across two checks at least six hours apart. Persist the URL,
times, normalized names, event/date fingerprint, and operator. A changed
fingerprint or degraded run goes to manual review; it does not auto-retry.

After the hold:

- Discovery/core target: **at or below $0.10/race**; alert above $0.15 and stop
  the cohort if any run exceeds $0.25.
- Full issues for a settled two-candidate field: plan at $0.60, alert above
  $0.75, and stop/degrade at $1.25 unless overridden.
- Run two representative pilots first; both must pass roster, health, validation,
  and cost gates. Review every later cohort of at most five.
- Count failed/cancelled spend and classify workflow from `enabled_steps`.

| Envelope | Cap |
| --- | ---: |
| All-race post-primary discovery/core | $65 |
| Remaining competitive issues | $50 |
| Corrections/reviewed retries | $35 |
| Demand-led expansion | $40 |
| Uncommitted reserve | $110 |
| **Total ceiling** | **$300** |

Show `current_field_ceiling`, `post_primary_scenario_estimate`, and observed
cost separately. The $300 is a ceiling, not a target.

## API, MCP, and admin work

Build in this order:

1. **Coverage/event manifest and admission guard.** Store race ID, cycle,
   office, event type/date, primary/runoff date, official source, disposition,
   and sourced special-election override. Queue/research/publish reject IDs
   outside it. Today `queue_races` validates only syntax and can create a race.
2. **Result checkpoints.** Add protected writes and cached reads for official
   checks and fingerprints. Checkpoint writes never queue work.
3. **Canonical status read.** Join manifest, checkpoint, active work, published
   health, latest repair gaps, rating, separate demand signals, and program
   spend. Every field declares `manifest`, `published`, `draft`, or `latest`
   provenance.
4. **MCP.** Add read-only `get_research_program_status` and explicit
   `record_research_result_checkpoint`; internalize pagination and the valid
   denominator. Keep `refresh_race_core` as the canonical run operation.
5. **Admin.** Add coverage validity, result/discovery/issue states, event date,
   blockers, candidates, estimates, actual spend, provenance, filters, and a
   checkpoint editor to Races. Add envelope/cohort cost controls to Costs.
6. **Metrics.** Classify by steps, include failed/cancelled spend, configure GCP
   billing export, and keep Cloudflare/Bing/Google/API demand separate.

The admin catalog currently exposes no `contest_stage`, `election_stage`,
`primary_date`, or `event_type`. `scan_catalog` reads published/admin health;
`audit_issue_research_readiness` uses latest repair artifacts but combines them
with catalog metadata. Their validation/roster/issue counts diverge when drafts
exist. The canonical status endpoint must not silently mix those views.

Required lifecycle:

| Discovery | Issues | Action |
| --- | --- | --- |
| `waiting_event` / `stabilizing` | `blocked_roster` | Check result |
| `ready` | `blocked_roster` | Eligible for authorized core refresh |
| `queued` / `running` | `blocked_roster` | Monitor; never duplicate |
| `review_required` | `blocked_roster` | Review evidence, health, and cost |
| `complete` | `ready` | Eligible for authorized issues |
| `complete` | issue lifecycle | Queue/monitor/review issues |
| `manual_review` | `manual_review` | Resolve named exception |

Until this ships, use the read-only issue audit, all `scan_catalog` pages,
active runs/queue, and an official result check. `recheck_all_races` mutates
state and is not a tracker read.

The program is complete when all 507 manifest races have a disposition, every
applicable race has reviewed discovery matching its stable fingerprint, every
then-current competitive race has reviewed complete issues, exceptions are
resolved/accepted, and attributable spend is at or below $300.
