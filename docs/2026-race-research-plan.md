# 2026 Race Research and Refresh Plan

Status: Active through the 2026 general-election cycle.

Last calendar review: 2026-08-09.

Last deployed-data audit: 2026-08-09 against the dev races API. Re-run the
read-only audit before using any count or race classification below.

## Objective

Keep every covered race's candidate roster, polling, and forecast current while
spending issue-research budget where it has the most voter value. This plan
separates three kinds of work that should not share one cadence:

1. **Discovery** is event-driven roster verification.
2. **Polling and forecast** are time-sensitive maintenance.
3. **Issue research** is comparatively expensive candidate-level work that
   should run only after the advancing field is known, except where voters face
   a pre-general open primary such as Louisiana's U.S. House elections.

The commands, queue semantics, review gates, and publication rules remain
canonical in [pipeline-operations.md](pipeline-operations.md). This document
only defines the 2026 schedule and prioritization policy. It does not authorize
queueing paid research or publishing drafts.

## Executive decision

Do not attempt a catalog-wide full rerun. On the 2026-08-09 snapshot, the
deterministic repair planner estimated a **$1,273.14 ceiling** and **187,520
search calls** to repair all currently analyzable records. Those figures are
ceilings based on today's mostly pre-primary rosters; they should fall after
primary losers are removed. Work in small, sequential units:

- complete post-primary discovery for every race
- fund missing issue research first in competitive races
- refresh polling and forecasts on a competitiveness-based cadence
- preserve good issue research for advancing candidates
- treat stale issue evidence produced by older pipeline runs as a targeted
  refinement/review backlog, not an automatic full rewrite

## Schedule at a glance

| Period | Discovery | Issues | Polling + forecast |
| --- | --- | --- | --- |
| Aug. 10-17 | HI, then AL/CT/MN/VT/WI after results; also verify the next issue race before researching it | One competitive race at a time, starting at the top of the exact queue | Aug. 14: eligible tossup/tilt groups |
| Aug. 19-Sep. 18 | AK, FL, WY, affected OK races, MA, NH, RI, then DE on its certification date | Continue competitive queue; newly settled races join according to rating | Weekly tossup/tilt; alternate lean rotations |
| Sep. 21-Oct. 2 | Competitive roster exceptions only | Finish competitive issue gaps or record a named blocker | Full competitive refresh across Sep. 28-Oct. 2 |
| Oct. 5-16 | Event-driven; verify LA House fields Oct. 12-16 | Likely/open-seat races, except LA viable candidates take priority Oct. 12-16 | Weekly tossup/tilt and alternating lean rotation |
| Oct. 19-28 | Catalog-wide check; queue only actual roster changes | Continue approved likely races; stop starting broad work after Oct. 28 | Weekly rotation, then all competitive races Oct. 26-28 |
| Oct. 29-Nov. 6 | Emergency corrections; narrow LA runoff fields Nov. 4-6 | No new broad work; preserve/fill only LA runoff-candidate research | Event-driven only, plus affected LA refresh |

### Immediate next work

1. Re-run the read-only audit and resolve whether the four snapshot “running”
   records are genuinely active or stale catalog status.
2. Triage the missing artifacts for `nd-senate-2026`, `ut-governor-2026`, and
   `vt-senate-2026` before treating those races as researchable.
3. Run Hawaii discovery after official results are decisive.
4. Verify the post-primary roster for `tx-senate-2026`, the first eligible race
   in the competitive issue queue.
5. If that discovery passes, run its ordered issue repair plan and finalization;
   review the draft and actual cost before selecting queue position 2.
6. On Aug. 11, do not research same-day primary fields. Beginning Aug. 12,
   discovery for AL/CT/MN/VT/WI takes precedence over the older roster backlog.

## Source-of-truth audit

Use the MCP tool below before planning a cohort:

```text
audit_issue_research_readiness(
  include_rows=true,
  include_schedule=true,
  traffic_hours=720,
  batch_size=50
)
```

Omit `race_ids` to audit the entire admin catalog. The output has three useful
views:

- `rows` is the race-by-race inventory: roster evidence, issue coverage,
  validation, freshness, rating, recent demand, and repair ceiling.
- `issue_queue` orders every issue-incomplete race by forecast rating, then by
  the larger of recent pageviews or race-API requests. It is a priority list,
  not permission to queue the list in bulk.
- `refresh_groups` divides current tossup/tilt and lean races into deterministic
  groups of no more than five. Apply the dated rotation below to these current
  groups instead of maintaining a second hand-written race list.

Set `include_rows=false` only when the summary and generated queues are enough,
or pass an explicit `race_ids` list for a primary cohort. The tool reads the
latest draft before falling back to published data, batches repair-plan
requests, tolerates unavailable analytics, and does not mutate or queue
anything. Its stored-roster signal is not proof that a primary result has been
verified; official results remain a separate gate.

### Catalog-wide snapshot

The deployed catalog contained 511 intended race records. Of those, 508 had a
draft or published RaceJSON available for analysis. These three catalog records
had no retrievable artifact and must be repaired before research is planned:

- `nd-senate-2026`
- `ut-governor-2026`
- `vt-senate-2026`

The catalog also contained `chamber_forecasts`; it is an aggregate artifact,
not a race, and is excluded from all counts below.

Across the 508 analyzable races:

| Measure | Count |
| --- | ---: |
| Candidate profiles | 1,613 |
| Canonical issue slots | 19,356 |
| Terminal issue verdicts | 4,261 |
| Missing issue verdicts | 15,095 |
| Races with at least one missing issue | 429 |
| Races with complete stored issue coverage | 79 |
| Races with incomplete strong roster evidence | 256 |
| Races with a passing validation grade | 71 |
| Races needing roster verification before issue work | 205 |
| Races ready for issue planning after an official-result check | 224 |
| Races needing roster work but no new issue slots | 51 |
| Races needing only non-issue repair or review | 19 |
| Races with no planner-recommended repair | 9 |

Research tiers were 394 `discovery_only`, 33 `graded_low`, 71 `validated`, 3
`partial_research`, and 7 `full_unreviewed`. The high discovery-only count is
why issue-slot presence must not be confused with a verified general-election
profile.

The catalog showed four active runs at audit time
(`ak-senate-2026`, `fl-house-14-2026`, `ga-senate-2026`, and
`ia-senate-2026`). It also showed four failed runs, one cancelled run, and two
missing-artifact records with no run status. These are snapshot observations;
check live run state before queueing overlapping work.

### State-level audit

`Artifacts/catalog` distinguishes analyzable RaceJSON artifacts from intended
catalog records. `Roster gaps` counts races whose stored strong roster evidence
does not cover every current candidate; it does not replace a post-primary
official-results check.

| State | Artifacts/catalog | Issue-gap races | Missing issue slots | Roster gaps | Validated |
| --- | ---: | ---: | ---: | ---: | ---: |
| AK | 3/3 | 1 | 48 | 3 | 0 |
| AL | 9/9 | 6 | 156 | 5 | 4 |
| AR | 7/7 | 3 | 72 | 4 | 4 |
| AZ | 10/10 | 10 | 300 | 2 | 2 |
| CA | 53/53 | 47 | 1,177 | 5 | 7 |
| CO | 10/10 | 8 | 396 | 4 | 2 |
| CT | 6/6 | 6 | 252 | 3 | 0 |
| DE | 2/2 | 1 | 24 | 2 | 1 |
| FL | 30/30 | 24 | 1,284 | 20 | 3 |
| GA | 16/16 | 14 | 360 | 3 | 1 |
| HI | 3/3 | 3 | 216 | 1 | 0 |
| IA | 6/6 | 5 | 128 | 0 | 1 |
| ID | 4/4 | 3 | 96 | 4 | 1 |
| IL | 19/19 | 17 | 432 | 3 | 1 |
| IN | 9/9 | 8 | 300 | 1 | 1 |
| KS | 6/6 | 5 | 204 | 4 | 1 |
| KY | 7/7 | 6 | 228 | 1 | 1 |
| LA | 7/7 | 6 | 312 | 1 | 1 |
| MA | 11/11 | 10 | 420 | 5 | 1 |
| MD | 9/9 | 8 | 216 | 2 | 1 |
| ME | 4/4 | 3 | 96 | 0 | 2 |
| MI | 15/15 | 5 | 228 | 8 | 7 |
| MN | 10/10 | 9 | 480 | 6 | 0 |
| MO | 8/8 | 7 | 468 | 4 | 0 |
| MS | 5/5 | 5 | 180 | 3 | 1 |
| MT | 3/3 | 2 | 96 | 1 | 1 |
| NC | 15/15 | 12 | 456 | 4 | 1 |
| ND | 1/2 | 1 | 24 | 0 | 1 |
| NE | 5/5 | 4 | 144 | 1 | 1 |
| NH | 4/4 | 3 | 201 | 3 | 1 |
| NJ | 13/13 | 11 | 372 | 1 | 2 |
| NM | 5/5 | 4 | 84 | 1 | 1 |
| NV | 5/5 | 5 | 156 | 1 | 1 |
| NY | 27/27 | 24 | 636 | 20 | 3 |
| OH | 17/17 | 14 | 408 | 13 | 2 |
| OK | 7/7 | 6 | 156 | 6 | 1 |
| OR | 8/8 | 8 | 192 | 7 | 2 |
| PA | 18/18 | 18 | 481 | 12 | 0 |
| RI | 4/4 | 3 | 132 | 4 | 1 |
| SC | 9/9 | 8 | 240 | 8 | 1 |
| SD | 3/3 | 1 | 24 | 3 | 1 |
| TN | 11/11 | 9 | 384 | 11 | 1 |
| TX | 40/40 | 38 | 1,080 | 28 | 2 |
| UT | 5/6 | 4 | 124 | 5 | 1 |
| VA | 12/12 | 12 | 528 | 9 | 1 |
| VT | 2/3 | 1 | 24 | 2 | 0 |
| WA | 10/10 | 9 | 516 | 8 | 1 |
| WI | 9/9 | 8 | 396 | 8 | 1 |
| WV | 3/3 | 2 | 48 | 3 | 1 |
| WY | 3/3 | 2 | 120 | 3 | 0 |
| **Total** | **508/511** | **429** | **15,095** | **256** | **71** |

## Remaining primary and roster-finalization calendar

The general state calendar comes from the
[NCSL 2026 primary calendar](https://www.ncsl.org/elections-and-campaigns/2026-state-primary-election-dates),
with congressional dates cross-checked against the
[FEC calendar](https://www.fec.gov/resources/cms-content/documents/2026pdates.pdf).
Official state sources control when they differ or when a ballot-access detail
extends the practical roster deadline.

As of August 9, 406 covered catalog races were in states whose scheduled
primary/runoff window had passed. They still require the same data audit; a past
primary date is not evidence that SmarterVote's stored roster is current.

| Election or deadline | Covered cohort | Count | Earliest safe roster work |
| --- | --- | ---: | --- |
| Aug. 8 primary; results settling | HI governor and House 1-2 | 3 | Aug. 10, after official result pages identify winners |
| Aug. 11 primary | AL House 1, 2, 6, 7; CT; MN; VT; WI | 32 | Aug. 12-14, race by race |
| Aug. 18 primary | AK; FL; WY | 36 | AK/FL Aug. 19-21; WY Aug. 25 |
| Aug. 24 independent filing deadline | WY governor, House, Senate | 3 | Aug. 25, after the general field can be checked |
| Aug. 25 runoff | Affected OK governor, Senate, and House nominations | Up to 7 | Aug. 29, after the Aug. 28 withdrawal deadline |
| Sep. 1 primary | MA | 11 | Sep. 2-4 |
| Sep. 8 primary | NH | 4 | Sep. 9-11 |
| Sep. 9 primary | RI | 4 | Sep. 10-12 |
| Sep. 15 primary | DE | 2 | Sep. 18, the scheduled certification date |
| Nov. 3 open primary | LA House 1-6 | 6 | Research viable candidates before Nov. 3; prune Nov. 4 |
| Dec. 12 open general/runoff, if needed | Affected LA House races | Up to 6 | Dec. 13-16 for final archival updates |

Alaska uses a nonpartisan top-four primary, so discovery must retain the four
advancers rather than manufacture party nominees. Wyoming's official calendar
sets an August 24 independent-candidate deadline after its August 18 primary.
Oklahoma nominations that require a runoff remain unresolved through August 25,
and candidates may withdraw through August 28. Delaware schedules primary
certification for September 18.

Louisiana is the critical exception to the “wait until after the primary” rule.
Its U.S. House open primary occurs on November 3, when voters need candidate
information. Complete issue research for viable candidates by mid-October, then
use the November result to either retain a majority winner or narrow the profile
to the December 12 runoff field. The
[Louisiana Secretary of State](https://www.sos.la.gov/electionsandvoting/getelectioninformation/reviewtypesofelections/Pages/default.aspx)
describes the November open primary and possible December general election.

## Execution schedule

There are only three scheduled activities:

| Activity | When it runs | Queue size |
| --- | --- | ---: |
| **Discovery** | After an official primary/runoff result or final ballot deadline | Up to 5 races at a time |
| **Issues** | After discovery passes, starting with the highest-priority incomplete race | One race at a time |
| **Polling + forecast** | In the dated refresh windows below, after the roster is settled | Up to 5 races at a time |

One worker should have only one paid group running at a time. Do not preload a
week of work. When a run finishes, review its draft and cost before starting the
next row of work. `Issues` means the planner's candidate groups followed by one
finalization group; it never means an issues-only run.

### Normal workday order

This order answers what actually runs first when discovery, issues, and a
refresh are all due:

| Order | Work | Scope |
| ---: | --- | --- |
| 1 | Read-only audit | Active/failed runs, official-result readiness, current repair plan, and the day's refresh list |
| 2 | Discovery | One group of up to 5 races; newly completed primary cohorts take precedence over the older roster backlog |
| 3 | Draft check | Verify the discovery group before spending on any candidate in it |
| 4 | Issues | One race from the competitive issue queue; run its ordered candidate groups and finalization sequentially |
| 5 | Draft and cost check | The next issue race stays unqueued until this finishes |
| 6 | Second discovery group | Run only when the issue race is terminal or no eligible issue race is available |
| 7 | Polling + forecast | On a refresh date, process the due groups of 5 after higher-priority roster work; continue the remaining due groups the next workday |

The target while the roster backlog exists is **up to two discovery groups and
one issue race per workday**. This is a maximum, not a quota. A slow or failed
run consumes the slot; it does not justify queueing around the review gate.
Refresh work replaces the optional second discovery group before it displaces
the day's issue race.

### Master calendar

| Date range | Discovery | Issues | Polling + forecast |
| --- | --- | --- | --- |
| **Aug. 10** | Hawaii governor and House 1-2, if official results are decisive. Triage missing artifacts for ND Senate, UT governor, and VT Senate. | None until the integrity check and active-run check finish. | None. |
| **Aug. 11** | No same-day work on AL/CT/MN/VT/WI results. | Start one already-post-primary competitive race after confirming its roster. Continue one race at a time. | None. |
| **Aug. 12-17** | AL House 1,2,6,7; CT; MN; VT; WI. Process in state groups of no more than 5 races. | Continue older post-primary competitive races. Start a newly settled race only after its discovery draft passes. Review the four stale competitive Michigan profiles during this window. | **Fri. Aug. 14:** refresh currently settled tossup/tilt races in groups of 5. |
| **Aug. 18** | No same-day AK/FL/WY result work. | Continue only a race whose roster was verified before Aug. 18. | None. |
| **Aug. 19-24** | AK first. Then FL statewide races, followed by House districts in groups of 5. Carry uncertain or failed races forward individually. | Start verified AK/FL competitive races one at a time while discovery continues on the rest. | **Fri. Aug. 21:** refresh settled tossup/tilt races; include newly settled Aug. 11 races. |
| **Aug. 25-28** | WY after the Aug. 24 independent deadline. Hold Oklahoma runoff races through the Aug. 28 withdrawal deadline. | Continue verified competitive AK/FL/WY races one at a time. | **Fri. Aug. 28:** tossup/tilt refresh plus half of the lean races, all in groups of 5. |
| **Aug. 31-Sep. 4** | Affected OK races on Aug. 31. MA governor/Senate and House districts in groups of 5 beginning Sep. 2. | Continue the competitive queue; an OK or MA race enters only after discovery passes. | **Fri. Sep. 4:** tossup/tilt refresh plus the other half of lean races. |
| **Sep. 8-11** | NH beginning Sep. 9; RI beginning Sep. 10. Each state fits in one group of 4. | Continue one competitive race at a time. | **Fri. Sep. 11:** tossup/tilt plus first half of lean races. |
| **Sep. 15-18** | DE House and Senate on Sep. 18 after scheduled certification. | Continue one competitive race at a time; no DE issue work before discovery passes. | **Fri. Sep. 18:** tossup/tilt plus second half of lean races. |
| **Sep. 21-Oct. 2** | Event-driven corrections only. Re-audit every competitive roster. | Work only on missing competitive issues, one race at a time. By Oct. 2, every competitive race must be complete or have a named blocker. | **Fri. Sep. 25:** tossup/tilt plus first half of lean. **Sep. 28-Oct. 2:** refresh all competitive races across the week, in groups of 5. |
| **Oct. 5-9** | Event-driven corrections only. | Begin likely/open-seat races, one at a time, only within the approved budget. | **Fri. Oct. 9:** tossup/tilt plus second half of lean. Refresh likely races only where new evidence exists. |
| **Oct. 12-16** | Verify Louisiana House candidate fields in two groups: districts 1-3 and 4-6. Do not prune viable open-primary candidates. | Louisiana viable-candidate issues take precedence. Continue likely/open-seat work only when the LA queue is clear. Louisiana target: reviewed by Oct. 16. | **Fri. Oct. 16:** tossup/tilt plus first half of lean. |
| **Oct. 19-23** | Catalog-wide read-only roster check; queue only actual changes. | Continue approved likely/open-seat races one at a time. | Event-driven corrections only. Do not spend on an Oct. 23 cycle three days before the final pass. Verify voter-resource links. |
| **Oct. 26-28** | Event-driven corrections only. | Finish work already close to review. Do not start broad new issue research after Oct. 28. | Refresh all tossup/tilt/lean races in groups of 5 across Oct. 26-28. |
| **Oct. 29-Nov. 2** | Emergency factual corrections only. | No new issue research. Review, retry, and prepare publication decisions. | Refresh only when a new poll or material event justifies changing a stable forecast. |
| **Nov. 3** | General Election and LA House open primary; monitor only. | None. | None. |
| **Nov. 4-6** | Narrow LA House 1-3 and 4-6 to a majority winner or the two runoff candidates. | Preserve retained-candidate research; fill only genuinely missing runoff-candidate issues. | Refresh affected LA polling and forecasts after discovery passes. |
| **Dec. 13-16** | Final LA runoff roster/archive updates where required. | No broad new issue research. | Final affected-race forecast/archive update. |

### Exact remaining-primary discovery groups

Queue one row at a time. Dates remain conditional on the official-result gate.

| Earliest | Group | Race IDs |
| --- | --- | --- |
| Aug. 10 | Hawaii | `hi-governor-2026`, `hi-house-01-2026`, `hi-house-02-2026` |
| Aug. 12 | Delayed Alabama House | `al-house-01-2026`, `al-house-02-2026`, `al-house-06-2026`, `al-house-07-2026` |
| Aug. 12 | Connecticut statewide/House 1-4 | `ct-governor-2026`, `ct-house-01-2026`, `ct-house-02-2026`, `ct-house-03-2026`, `ct-house-04-2026` |
| Aug. 12 | Connecticut House 5 | `ct-house-05-2026` |
| Aug. 12 | Minnesota statewide/House 1-3 | `mn-governor-2026`, `mn-senate-2026`, `mn-house-01-2026`, `mn-house-02-2026`, `mn-house-03-2026` |
| Aug. 12 | Minnesota House 4-8 | `mn-house-04-2026`, `mn-house-05-2026`, `mn-house-06-2026`, `mn-house-07-2026`, `mn-house-08-2026` |
| Aug. 12 | Vermont | `vt-governor-2026`, `vt-house-2026`; restore `vt-senate-2026` before adding it |
| Aug. 12 | Wisconsin statewide/House 1-3 | `wi-governor-2026`, `wi-house-01-2026`, `wi-house-02-2026`, `wi-house-03-2026` |
| Aug. 12 | Wisconsin House 4-8 | `wi-house-04-2026`, `wi-house-05-2026`, `wi-house-06-2026`, `wi-house-07-2026`, `wi-house-08-2026` |
| Aug. 19 | Alaska | `ak-governor-2026`, `ak-house-2026`, `ak-senate-2026` |
| Aug. 19 | Florida statewide | `fl-governor-2026`, `fl-senate-2026-special` |
| Aug. 19 | Florida House 1-5 | `fl-house-01-2026` through `fl-house-05-2026` |
| Aug. 19 | Florida House 6-10 | `fl-house-06-2026` through `fl-house-10-2026` |
| Aug. 19 | Florida House 11-15 | `fl-house-11-2026` through `fl-house-15-2026` |
| Aug. 19 | Florida House 16-20 | `fl-house-16-2026` through `fl-house-20-2026` |
| Aug. 19 | Florida House 21-24 | `fl-house-21-2026` through `fl-house-24-2026` |
| Aug. 19 | Florida House 25-28 | `fl-house-25-2026` through `fl-house-28-2026` |
| Aug. 25 | Wyoming | `wy-governor-2026`, `wy-house-2026`, `wy-senate-2026` |
| Aug. 31 | Oklahoma statewide | Affected subset of `ok-governor-2026`, `ok-senate-2026` from the official runoff list |
| Aug. 31 | Oklahoma House | Affected subset of `ok-house-01-2026` through `ok-house-05-2026` from the official runoff list |
| Sep. 2 | Massachusetts statewide/House 1-3 | `ma-governor-2026`, `ma-senate-2026`, `ma-house-01-2026`, `ma-house-02-2026`, `ma-house-03-2026` |
| Sep. 2 | Massachusetts House 4-8 | `ma-house-04-2026` through `ma-house-08-2026` |
| Sep. 2 | Massachusetts House 9 | `ma-house-09-2026` |
| Sep. 9 | New Hampshire | `nh-governor-2026`, `nh-senate-2026`, `nh-house-01-2026`, `nh-house-02-2026` |
| Sep. 10 | Rhode Island | `ri-governor-2026`, `ri-senate-2026`, `ri-house-01-2026`, `ri-house-02-2026` |
| Sep. 18 | Delaware | `de-house-2026`, `de-senate-2026` |
| Oct. 12 | Louisiana pre-primary verification | `la-house-01-2026`, `la-house-02-2026`, `la-house-03-2026` |
| Oct. 12 | Louisiana pre-primary verification | `la-house-04-2026`, `la-house-05-2026`, `la-house-06-2026` |

#### Dated discovery batch ledger

The `Earliest` column above is a legal/data-readiness boundary. This ledger is
the actual target sequence. A slot contains one discovery run of no more than
five races. If official results are not decisive, mark the slot `held`, record
the official source checked, and retry it the next business day; do not move
issue work for that cohort ahead of it.

| Target date | Discovery slot 1 | Discovery slot 2 | Notes |
| --- | --- | --- | --- |
| Mon. Aug. 10 | Hawaii | Missing-artifact triage, not a paid run | Issue research remains closed until triage and active-run checks finish. |
| Wed. Aug. 12 | Delayed Alabama House | Connecticut statewide/House 1-4 | First post-Aug. 11 result day. |
| Thu. Aug. 13 | Connecticut House 5 | Minnesota statewide/House 1-3 | Review both drafts before Friday work. |
| Fri. Aug. 14 | Minnesota House 4-8 | None | Reserve remaining capacity for the first tossup/tilt refresh cycle. |
| Mon. Aug. 17 | Vermont | Wisconsin statewide/House 1-3 | Restore VT Senate before including it. |
| Tue. Aug. 18 | Wisconsin House 4-8 | None | Monitor AK/FL/WY results; do not run same-day discovery there. |
| Wed. Aug. 19 | Alaska | Florida statewide | Alaska must retain all four primary advancers. |
| Thu. Aug. 20 | Florida House 1-5 | Florida House 6-10 | Stop the cohort on any systemic roster problem. |
| Fri. Aug. 21 | Florida House 11-15 | None | Reserve remaining capacity for the tossup/tilt cycle. |
| Mon. Aug. 24 | Florida House 16-20 | Florida House 21-24 | Wyoming remains held through its independent deadline. |
| Tue. Aug. 25 | Florida House 25-28 | Wyoming | Verify the full Wyoming general field, not only primary winners. |
| Mon. Aug. 31 | Affected Oklahoma statewide races | Affected Oklahoma House races | Determine the affected subset from official runoff and withdrawal records. |
| Wed. Sep. 2 | Massachusetts statewide/House 1-3 | None | First result-review day. |
| Thu. Sep. 3 | Massachusetts House 4-8 | Massachusetts House 9 | — |
| Wed. Sep. 9 | New Hampshire | None | — |
| Thu. Sep. 10 | Rhode Island | None | — |
| Fri. Sep. 18 | Delaware | None | Wait for scheduled certification. |
| Mon. Oct. 12 | Louisiana House 1-3 verification | None | Preserve every viable open-primary candidate. |
| Tue. Oct. 13 | Louisiana House 4-6 verification | None | Issue repairs for LA may begin only after each draft passes. |
| Wed. Nov. 4 | Louisiana House 1-3 pruning | None | Retain a majority winner or the two runoff candidates. |
| Thu. Nov. 5 | Louisiana House 4-6 pruning | None | Refresh only affected races afterward. |
| Mon.-Tue. Dec. 14-15 | Affected Louisiana runoff races | None | Split into groups of five if more than five require archival work. |

Unfilled discovery slots are deliberate slack for held results, retries, and
draft review. Do not fill them by pulling a future-primary cohort forward.

### Issue queue order

The issue worker has **one start slot on every business day from Aug. 11 through
Oct. 28**, except a day reserved for same-day election monitoring or a day when
the previous issue repair is still active or awaiting review. The start slot
opens only after that day's discovery draft checks. Select exactly one next
eligible race in this order:

1. tossup with missing issues
2. tilt with missing issues
3. lean with missing issues
4. a competitive race with stale complete issues
5. likely open-seat or statewide race
6. likely race with demonstrated traffic
7. other likely race
8. safe statewide/open-seat race, only if budget remains

Do not reserve a fixed number of issue races for a week. Candidate counts and
run duration vary too much. The queue advances only when the previous race's
candidate groups, finalization, and draft review are complete.

Operationally, this means: audit Monday morning; attempt one issue start each
eligible weekday; never overlap issue races; and on Friday record the highest
queue position completed, actual weekly spend, failures, and the first eligible
race for Monday. A missed start slot is not backfilled with two simultaneous
issue races the next day.

### Exact competitive issue queue

This is the deployed queue snapshot from 2026-08-09 after the active catalog
changed during the audit. `Earliest` is the first date on which discovery may
establish the relevant field; it is not permission to skip the official-result
gate. `Roster stored` describes existing evidence only. Every row still needs a
post-primary result check before issue spending.

| Order | Race | Rating | Earliest | Missing issue slots | Roster stored |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `tx-senate-2026` | Tossup | Aug. 10 | 12 | Complete |
| 2 | `wi-governor-2026` | Tossup | Aug. 12 | 84 | Incomplete |
| 3 | `nc-house-11-2026` | Tossup | Aug. 10 | 48 | Complete |
| 4 | `tx-house-15-2026` | Tossup | Aug. 10 | 24 | Complete |
| 5 | `va-house-01-2026` | Tossup | Aug. 10 | 24 | Complete |
| 6 | `pa-house-08-2026` | Tossup | Aug. 10 | 1 | Complete |
| 7 | `nv-governor-2026` | Tossup | Aug. 10 | 12 | Complete |
| 8 | `oh-governor-2026` | Tossup | Aug. 10 | 48 | Complete |
| 9 | `tx-house-34-2026` | Tossup | Aug. 10 | 48 | Complete |
| 10 | `tx-house-35-2026` | Tossup | Aug. 10 | 24 | Complete |
| 11 | `ks-governor-2026` | Tilt R | Aug. 10 | 24 | Incomplete |
| 12 | `mi-house-04-2026` | Tilt R | Aug. 10 | 36 | Complete |
| 13 | `nj-house-02-2026` | Tilt R | Aug. 10 | 36 | Complete |
| 14 | `ia-governor-2026` | Tilt D | Aug. 10 | 8 | Complete |
| 15 | `tx-house-23-2026` | Tilt R | Aug. 10 | 36 | Complete |
| 16 | `mo-house-02-2026` | Lean R | Aug. 10 | 96 | Complete |
| 17 | `ks-house-03-2026` | Lean D | Aug. 10 | 36 | Complete |
| 18 | `mo-house-05-2026` | Lean R | Aug. 10 | 96 | Complete |
| 19 | `va-house-02-2026` | Lean D | Aug. 10 | 60 | Complete |
| 20 | `ak-house-2026` | Lean R | Aug. 19 | 48 | Incomplete |
| 21 | `mo-house-04-2026` | Lean R | Aug. 10 | 36 | Complete |
| 22 | `az-01-house-2026` | Lean D | Aug. 10 | 36 | Complete |
| 23 | `fl-house-13-2026` | Lean R | Aug. 19 | 60 | Complete |
| 24 | `fl-house-07-2026` | Lean R | Aug. 19 | 96 | Complete |
| 25 | `ny-house-01-2026` | Lean R | Aug. 10 | 48 | Complete |
| 26 | `tx-governor-2026` | Lean R | Aug. 10 | 24 | Complete |
| 27 | `ca-house-22-2026` | Lean D | Aug. 10 | 24 | Complete |
| 28 | `fl-house-27-2026` | Lean R | Aug. 19 | 48 | Complete |
| 29 | `nc-house-08-2026` | Lean R | Aug. 10 | 36 | Complete |
| 30 | `nh-governor-2026` | Lean R | Sep. 9 | 60 | Incomplete |
| 31 | `pa-house-01-2026` | Lean R | Aug. 10 | 48 | Complete |
| 32 | `pa-house-07-2026` | Lean D | Aug. 10 | 60 | Complete |
| 33 | `pa-house-10-2026` | Lean D | Aug. 10 | 36 | Complete |
| 34 | `ne-senate-2026` | Lean R | Aug. 10 | 36 | Complete |
| 35 | `ga-governor-2026` | Lean D | Aug. 10 | 24 | Complete |
| 36 | `nv-house-03-2026` | Lean D | Aug. 10 | 36 | Complete |
| 37 | `az-06-house-2026` | Lean D | Aug. 10 | 36 | Complete |
| 38 | `az-house-02-2026` | Lean R | Aug. 10 | 24 | Complete |
| 39 | `co-house-03-2026` | Lean R | Aug. 10 | 48 | Complete |
| 40 | `ga-house-13-2026` | Lean D | Aug. 10 | 24 | Incomplete |
| 41 | `ia-house-01-2026` | Lean D | Aug. 10 | 36 | Complete |
| 42 | `ia-house-02-2026` | Lean R | Aug. 10 | 24 | Complete |
| 43 | `ia-house-03-2026` | Lean D | Aug. 10 | 24 | Complete |
| 44 | `ia-house-04-2026` | Lean R | Aug. 10 | 36 | Complete |
| 45 | `il-house-06-2026` | Lean D | Aug. 10 | 24 | Complete |
| 46 | `il-house-08-2026` | Lean D | Aug. 10 | 24 | Complete |
| 47 | `md-house-06-2026` | Lean D | Aug. 10 | 36 | Complete |
| 48 | `me-house-02-2026` | Lean R | Aug. 10 | 24 | Complete |
| 49 | `mt-house-01-2026` | Lean R | Aug. 10 | 48 | Complete |
| 50 | `nh-house-02-2026` | Lean D | Sep. 9 | 84 | Complete |
| 51 | `ny-04-house-2026` | Lean D | Aug. 10 | 36 | Complete |
| 52 | `ny-house-17-2026` | Lean D | Aug. 10 | 24 | Complete |
| 53 | `oh-house-01-2026` | Lean D | Aug. 10 | 36 | Complete |
| 54 | `or-house-04-2026` | Lean D | Aug. 10 | 24 | Complete |
| 55 | `va-house-05-2026` | Lean R | Aug. 10 | 48 | Complete |
| 56 | `wa-house-03-2026` | Lean D | Aug. 10 | 24 | Complete |
| 57 | `wi-house-03-2026` | Lean D | Aug. 12 | 60 | Complete |
| 58 | `nj-house-07-2026` | Lean D | Aug. 10 | 36 | Complete |
| 59 | `nm-house-03-2026` | Lean D | Aug. 10 | 24 | Complete |
| 60 | `nv-house-02-2026` | Lean R | Aug. 10 | 36 | Complete |

The ordering uses rating first and observed demand second, then race ID. When a
higher row is not yet eligible, blocked, active, or awaiting review, take the
next eligible row. Re-run the audit every Monday and after each primary cohort;
add newly competitive incomplete races and remove races whose rating or issue
coverage changed.

### Refresh rotation

- **Tossup and tilt:** every listed refresh Friday after the roster settles.
- **Lean:** alternate halves each Friday; all lean races receive a refresh every
  two weeks. Refresh all of them during the Oct. 26-28 final pass.
- **Likely:** once after the primary, then only after new polling, a material
  event, or demonstrated traffic.
- **Safe:** once after the primary. Thereafter refresh only for a roster change,
  new meaningful evidence, or data older than 45 days near Election Day.

#### Tossup/tilt groups

Start all six eligible groups on Aug. 14, Aug. 21, Aug. 28, Sep. 4, Sep. 11,
Sep. 18, Sep. 25, Oct. 2, Oct. 9, and Oct. 16. Each date anchors a cycle of no
more than three business days: groups 1-2 on cycle day 1, groups 3-4 on day 2,
and groups 5-6 on day 3. Run the final cycle Oct. 26-28. There is deliberately
no Oct. 23 cycle because it would duplicate the final pass three days later.
Skip a race until its roster settles; do not substitute issue work for the
skipped refresh.

| Group | Race IDs |
| --- | --- |
| Tossup/tilt 1 | `ak-governor-2026`, `ak-senate-2026`, `al-house-02-2026`, `ca-house-48-2026`, `co-house-08-2026` |
| Tossup/tilt 2 | `fl-house-14-2026`, `fl-house-25-2026`, `ia-governor-2026`, `ks-governor-2026`, `ky-house-06-2026` |
| Tossup/tilt 3 | `me-senate-2026`, `mi-07-house-2026`, `mi-house-04-2026`, `mi-house-10-2026`, `mi-senate-2026` |
| Tossup/tilt 4 | `nc-house-01-2026`, `nc-house-11-2026`, `nj-house-02-2026`, `nv-governor-2026`, `oh-governor-2026` |
| Tossup/tilt 5 | `oh-senate-2026-special`, `pa-house-08-2026`, `tx-house-15-2026`, `tx-house-23-2026`, `tx-house-34-2026` |
| Tossup/tilt 6 | `tx-house-35-2026`, `tx-senate-2026`, `va-house-01-2026`, `wi-governor-2026` |

#### Lean groups

Run rotation A in the cycles beginning Aug. 28, Sep. 11, Sep. 25, and Oct. 9.
Run rotation B in the cycles beginning Sep. 4, Sep. 18, Oct. 2, and Oct. 16.
Run both rotations once more across Oct. 26-28.

Rotation A has six groups: run A1/A3 on cycle day 1, A5/A7 on day 2, and
A9/A11 on day 3. Rotation B has five groups: run B2/B4 on day 1, B6/B8 on day
2, and B10 on day 3. On weeks when tossup/tilt and lean are both due, process
the tossup/tilt pair first each day, review it, and then process the lean pair.
No queued group may contain more than five races.

| Rotation | Group | Race IDs |
| --- | --- | --- |
| A | Lean 1 | `ak-house-2026`, `ar-house-02-2026`, `az-01-house-2026`, `az-06-house-2026`, `az-house-02-2026` |
| B | Lean 2 | `ca-house-01-2026`, `ca-house-22-2026`, `co-house-03-2026`, `fl-house-07-2026`, `fl-house-13-2026` |
| A | Lean 3 | `fl-house-22-2026`, `fl-house-27-2026`, `ga-governor-2026`, `ga-house-13-2026`, `ia-house-01-2026` |
| B | Lean 4 | `ia-house-02-2026`, `ia-house-03-2026`, `ia-house-04-2026`, `ia-senate-2026`, `il-house-06-2026` |
| A | Lean 5 | `il-house-08-2026`, `ks-house-03-2026`, `md-house-06-2026`, `me-house-02-2026`, `mi-governor-2026` |
| B | Lean 6 | `mi-house-11-2026`, `mo-house-02-2026`, `mo-house-04-2026`, `mo-house-05-2026`, `mt-house-01-2026` |
| A | Lean 7 | `nc-house-08-2026`, `ne-house-02-2026`, `ne-senate-2026`, `nh-governor-2026`, `nh-house-02-2026` |
| B | Lean 8 | `nj-house-07-2026`, `nm-house-03-2026`, `nv-house-02-2026`, `nv-house-03-2026`, `ny-04-house-2026` |
| A | Lean 9 | `ny-house-01-2026`, `ny-house-17-2026`, `oh-house-01-2026`, `oh-house-09-2026`, `or-house-04-2026` |
| B | Lean 10 | `pa-house-01-2026`, `pa-house-07-2026`, `pa-house-10-2026`, `tx-governor-2026`, `va-house-02-2026` |
| A | Lean 11 | `va-house-05-2026`, `wa-house-03-2026`, `wi-house-03-2026` |

The first task each refresh day is to generate the due race list from the live
catalog. The groups above are the 2026-08-09 starting snapshot. Apply rating
changes before queueing: remove races no longer in the band and place newly
competitive races into the smallest applicable group.

## Result-readiness gate

A date alone never unlocks issue research. A race enters post-primary work only
when all of these are true:

- an official election authority exposes current-cycle results for the exact
  office and district
- the advancing candidates can be determined under that state's rules
- no required runoff remains unresolved
- the independent/minor-party filing deadline needed to establish the general
  field has passed
- a close race, recount, withdrawal, disqualification, or legal challenge is
  not reasonably capable of changing the field
- the race identity and `contest_stage` can be recorded accurately

An AP call or candidate concession may guide monitoring, but official results
or a certified/qualified general-election candidate list must support roster
finalization. If the gate is uncertain, run no issue research for that race and
recheck the next business day.

## Work order for each cohort

### 1. Read-only audit

Run `audit_issue_research_readiness` for the cohort. Also inspect active runs so
the same race is not queued twice. Resolve missing artifacts and failed/cancelled
runs before interpreting their coverage.

### 2. Roster settlement

For every race whose primary field changed, run discovery against the published
baseline with `force_fresh=false`. Use groups of no more than five races. The
discovery result must:

- remove defeated candidates
- retain every nominee or lawful advancer
- include independent/minor-party candidates who qualified for the general
- cite exact-contest current-cycle result or ballot evidence
- set `contest_stage` correctly
- provide substantive, sourced summaries for the retained field

Do not infer that stored strong roster evidence is post-primary evidence. It may
correctly prove a candidate belonged to the earlier primary.

### 3. Re-plan after discovery

Run `audit_issue_research_readiness` again. Candidate removals should reduce the
issue-slot count and estimated cost. Preserve complete issue records for retained
candidates. Queue only the planner's ordered repair groups:

1. roster group first
2. candidate issue/finance/refinement groups independently
3. polling/forecast/voter-resources/review/iteration finalization once, last

Never queue `issues` alone. Use `baseline_source="latest"` for candidate and
finalization groups so each group builds on the verified draft.

### 4. Review and publication gate

After every run, inspect the draft and require:

- `validation_grade.passed == true`
- no literal placeholder content
- all retained candidates have exact-contest roster evidence and summaries
- every issue is either a sourced stance or the exact documented-absence marker
- finance and incumbent voting fields are populated and sourced
- polling and forecast candidates match the settled roster
- `assess_publish_readiness` reports no blocker

Publishing remains an explicit separate approval.

## Issue-research priority and budget

Current forecast bands divide the 508 analyzable races into 82 competitive, 115
likely, 309 safe, and 2 unrated races. Forecasts are themselves provisional
until post-primary refresh, so reclassify a race after discovery and forecast
work.

| Priority | Current scope with missing issues | Current repair ceiling | Target |
| --- | ---: | ---: | --- |
| P0: tossup, tilt, or lean | 60 races | $183.43 | Complete or name a blocker within seven days of roster settlement; catalog gate Oct. 2 |
| P1: likely | 95 races | $279.89 | Open seats and demonstrated traffic first; work through Oct. 28 within budget |
| P2: safe | 273 races | $763.73 | Statewide/open-seat/high-traffic first; continue only within approved budget |
| P0-triage: unrated | 2 races | $8.54 | Repair forecast/identity, then reclassify |

These are repair-plan ceilings, not forecasts of actual spend, and include the
other required repair steps around issue work. Primary roster cleanup should
lower them. Approve and run one issue race at a time, with a $25 ceiling for its
complete ordered repair plan. Review quality and actual cost before authorizing
the next race.

### Scheduled spend envelope

| Work | Planning amount | Interpretation |
| --- | ---: | --- |
| One post-primary core refresh for all 511 intended races | About $46 | Uses the rough $0.09/race operating figure; spread across each state's roster date, never queued catalog-wide |
| Exact 60-race competitive issue queue | $183.43 ceiling | Re-plan after discovery; removing primary losers should lower this |
| Scheduled competitive polling/forecast rotation | About $52.56 | Conservative proxy using $0.09 for 584 scheduled race-refresh slots; standalone polling/forecast should usually cost less than a core refresh |
| **Minimum roster + competitive plan** | **About $282, plus retries/artifact repair** | Review actual cost weekly; this is the budget to protect first |
| Add all currently incomplete likely races | Up to $279.89 more | Optional; run one race at a time through Oct. 28 |
| Add all currently incomplete safe races | Up to $763.73 more | Lowest priority and not assumed in the dated schedule |

The minimum amount is not a pre-authorization to spend. It is the envelope the
calendar was designed around. Stop between races when actual cost or quality
departs materially from the plan.

If the budget cannot fund every missing issue slot before voting begins, the
minimum viable order is:

1. competitive races
2. competitive races with stale issue evidence
3. likely open-seat and statewide races
4. races with actual user traffic
5. remaining likely races
6. safe races

Do not convert budget exhaustion into invented positions or mass “No public
position found” markers. Incomplete research remains visibly incomplete.

## Older issue research

Evidence freshness is a useful proxy for “generated on older code,” but it does
not prove poor quality. The published catalog had 29 races with complete but
stale issue evidence. Four are currently competitive and should receive prompt
refinement/review after roster verification:

- `mi-governor-2026`
- `mi-house-10-2026`
- `mi-house-11-2026`
- `mi-07-house-2026`

The remaining 25 stale-complete profiles are likely or safe. Keep their issue
records unless a spot audit finds unsupported claims, broken sources, weak
documented absences, or a material candidate-position change. Refresh sources
with `refinement` and run review/iteration; do not automatically pay to rerun all
12 issues from scratch.

## Per-run record

Record the following before marking discovery, issue research, or a refresh
complete:

- activity, date, and exact race IDs
- official result/ballot source where roster work occurred
- queue item and run IDs for every ordered group
- pre-run repair-plan ceiling and actual cost
- candidate additions/removals and resulting issue-slot count
- validation failures, retries, and unresolved blockers
- draft review and publication decision
- next scheduled polling/forecast date

Review this record every Monday before choosing the next issue race. A run that
finished its model calls but lacks draft review remains open.

## Completion criteria

The 2026 plan is complete when:

- every covered race has a verified current contest stage and general-election
  or lawful advancing roster
- the three missing artifacts are restored or intentionally retired
- every competitive race has reviewed issue coverage for every retained
  candidate
- remaining issue gaps have an explicit budget-backed disposition
- polling and forecast freshness matches the schedule above
- no failed, cancelled, or stale-running item is mistaken for completed work
- every publication was separately reviewed and approved

All ordinary covered primary calendars finish with Delaware on September 15,
subject to certification and disputes. Louisiana House nomination stages are
the exception: the open primary is November 3 and any required general/runoff is
December 12. Therefore December 12 is the last possible date on which every
covered race's nomination stage is over, but Louisiana issue research must be
available before November 3 to be useful to voters.
