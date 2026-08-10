# Pipeline Result Quality Plan

Last reviewed: 2026-07-26.

Delivered operational behavior is documented in
[`pipeline-operations.md`](pipeline-operations.md) and
[`PIPELINE_MODES.md`](../PIPELINE_MODES.md). This file remains the roadmap for
quality work that is still proposed.

## Objective

Improve the correctness of published race data by changing how the research
pipeline thinks, researches, and explains its work. This plan is about better
inputs and better process, not stricter publish gates.

The main failure pattern is not malformed JSON. It is plausible but wrong
research: candidates copied from a different office, primary fields mixed into
general-election races, stale Ballotpedia pages treated as authoritative, and
polished reviews approving profiles whose rosters are wrong.

## Principles

- Improve the agent's research behavior before validation.
- Prefer official election and filing sources over generic search snippets.
- Make race identity explicit before candidate discovery.
- Treat contest stage as first-class context.
- Preserve uncertainty instead of inventing candidate placeholders.
- Record why each candidate is in the roster, not only biographical facts.
- Keep draft-first publishing and existing admin review behavior unchanged.

## Observed Symptoms

Recent production data and run logs showed these recurring issues:

- Wrong-office contamination, such as a candidate from a Senate race appearing
  in a gubernatorial race because the name and state looked plausible.
- General-election profiles containing defeated or unresolved primary
  candidates.
- Forecasts using placeholder winners such as "Republican Candidate" when a
  nominee was unresolved.
- Ballotpedia fetches returning blocked or unusable content, followed by
  repeated attempts or overreliance on search snippets.
- Review agents approving well-written profiles while missing roster and office
  mismatch problems.
- Drafts containing useful corrections that are hard to triage because the
  remaining uncertainty is not summarized cleanly.

## Phase 1: Race Identity and Source Ladder

Status: Implemented.

### Problem

Discovery starts with a race ID and often searches for candidates before the
agent has explicitly fixed the office, state, district, election stage, and
available official sources. This lets the model drift into nearby races.

### Implementation

Before roster edits, discovery and roster sync should build an internal race
identity brief:

```json
{
  "office": "Governor",
  "state": "Alabama",
  "district": null,
  "contest_stage": "post_primary_general",
  "election_date": "2026-11-03",
  "primary_status": "completed",
  "official_roster_source_url": "https://...",
  "known_incumbent": "Kay Ivey",
  "known_ineligible_or_not_running": ["Kay Ivey"]
}
```

The prompt should use this source ladder for roster work:

1. Official state election authority, certified candidate list, ballot list, or
   official primary results.
2. Ballotpedia election page, if current and accessible.
3. FEC pages for federal races, only to corroborate federal candidates.
4. Reputable recent local/state news or official campaign announcements.

If Ballotpedia is blocked, stale, or primary-focused, the agent should pivot
instead of repeatedly fetching the same unusable page.

### Delivered So Far

- Fresh discovery now receives the current date.
- Discovery prompt now requires the agent to lock race identity before naming
  candidates, and returns the identity brief (office, state, district,
  contest stage, election date, primary status, official roster source,
  known incumbent, known ineligible/not-running people) as part of its JSON
  response, at `pipeline_state.race_identity`.
- Discovery and roster sync prompts now prefer official roster sources and tell
  the agent to avoid cross-office candidate transfer, following the source
  ladder from the plan: official state election authority / certified list /
  official primary results, then Ballotpedia (only if current and accessible),
  then FEC as federal corroboration only, then reputable recent local/state
  news or campaign announcements. Both prompts explicitly instruct the agent to
  stop retrying a blocked/stale/primary-focused Ballotpedia page and pivot up
  the ladder instead; `ballotpedia.py`'s `lookup_election_page` implements the
  matching runtime fallback (generated URL -> stable district URL -> search ->
  read-only proxy -> Wikipedia election article).
- The `set_race_identity` tool (used by roster sync / update runs) persists the
  identity brief into `pipeline_state.race_identity`, and the deterministic
  `_remove_known_ineligible_candidates` step enforces removal of anyone the
  model recorded there as ineligible/not-running, even if the model's own tool
  calls miss it.
- **Identity brief now feeds every later phase.** A single
  `phase_state.race_identity_context()` renders the locked brief (or an
  explicit "not yet locked" notice, or a fallback built from the race's own
  top-level office/state/district/contest_stage/election_date when no brief
  was recorded) and it is injected into the issue-research, finance/voting,
  polling, forecast, iteration (per-candidate and race-metadata), and
  multi-model review prompts — so a phase running later in a long batched run
  cannot drift onto a different office/state/district/election cycle than
  discovery locked in, and reviewers can audit the roster against the same
  locked identity instead of only the race title/description (`pipeline_state`
  is stripped from the semantic review packet as operational metadata, so this
  context is the reviewer's only view of the locked identity).
- Forecast prompt now avoids placeholder candidate winners.
- Review prompt now instructs reviewers to audit roster/office match before
  prose quality, using the locked identity as ground truth and flagging any
  candidate whose sources point to a different office/state/district/cycle or
  whose name appears in `known_ineligible_or_not_running`.
- Roster provenance is fully modeled and enforced: `Candidate.roster_sources`
  (`shared/models.py`) records evidence separate from `summary_sources`, and
  `add_candidate` grades each source into evidence tiers (1 = official/FEC
  content, 2 = dated campaign/exact-election Ballotpedia/news content, 3 =
  search snippet requiring two independent domains unless official/FEC),
  requiring an explicit `evidence` string that names the candidate and exact
  contest before a new candidate can be added. `add_candidate` also blocks a
  same-state candidate who is already registered as active in a *different*
  race (cross-office/cross-race contamination guard).
- Tests: `tests/test_race_identity_brief.py` covers `race_identity_context()`
  rendering (locked brief, top-level fallback, "not yet locked" notice, and a
  same-state wrong-office naming case) and confirms the locked identity reaches
  the issue-research, finance/polling/forecast, iteration, and review prompts.
  `tests/test_editing_tools.py::test_add_candidate_blocks_cross_race_contamination`
  and `tests/test_run_agent.py::test_sanitize_roster_removes_known_ineligible_from_race_identity`
  cover the same-state wrong-office and known-ineligible-removal scenarios.

### Remaining Work

None for this phase. Deeper contest-stage-aware candidate inclusion rules,
correction-goal decomposition, role-framed review sections, and post-run audit
notes are tracked separately under Phases 2-7 below.

## Phase 2: Contest Stage Semantics

Status: Implemented.

### Problem

The pipeline treats every race as if it were the same shape. In reality, 2026
contains pre-primary fields, post-primary general elections, runoffs,
top-two/top-four contests, ranked-choice races, and uncontested races. Mixing
these creates bad rosters and bad forecasts.

### Implementation

Add a race-level contest stage field, likely:

```text
pre_primary
post_primary_general
runoff
top_two
top_four_rcv
uncontested
unknown
```

Candidate inclusion should depend on contest stage:

- `pre_primary`: include verified active candidates across parties, with clear
  primary-field language.
- `post_primary_general`: include only nominees or candidates who advanced.
- `runoff`: include only runoff participants.
- `top_two`: include qualified finalists or active candidates under that system.
- `top_four_rcv`: include qualified top-four/RCV advancing candidates and avoid
  two-party assumptions.
- `uncontested`: include the verified candidate and explicitly state that no
  opponent filed if supported by an official source.
- `unknown`: avoid deleting candidates; summarize uncertainty and continue
  targeted discovery.

Do not create separate public pages for primaries yet unless product needs it.
This can start as internal metadata and prompt behavior.

### Acceptance Criteria

- Discovery determines contest stage before constructing the candidate roster.
- General-election profiles do not retain defeated primary candidates when
  primary results are available.
- Pre-primary races no longer pretend to have resolved general-election
  nominees.
- Forecasts can be party-level when nominees are unresolved.
- Alaska/top-four/ranked-choice races avoid accidental two-candidate cleanup.

## Phase 3: Candidate Provenance

Status: Implemented.

### Problem

Candidate biographies can be well-sourced while the reason for including the
candidate in this race is weak. Review then sees credible facts about the person
but misses that the person belongs to a different race or stage.

### Implementation

During discovery and roster sync, record candidate-level provenance:

```json
{
  "name": "Paige Cognetti",
  "party": "Democratic",
  "roster_source_url": "https://...",
  "roster_source_type": "official|ballotpedia|fec|news|campaign",
  "roster_source_title": "Candidate List",
  "roster_source_last_accessed": "2026-06-29T00:00:00Z",
  "roster_evidence": "Named as Democratic nominee for PA-08"
}
```

This provenance should be separate from `summary_sources`. A campaign bio proves
who the candidate is; roster provenance proves why they are in this race.

### Acceptance Criteria

- Every added candidate has at least one roster provenance entry.
- Roster review can inspect provenance without rereading all biographical
  sources.
- Wrong-office candidates become easier to catch because their provenance points
  to the wrong office or is absent.

## Phase 4: Correction Goals as First-Class Constraints

Status: Implemented.

### Problem

Human correction goals are often excellent, but later phases can dilute them
under generic research instructions.

### Implementation

When a run has a `goal`, convert it into explicit phase constraints:

```text
Correction goal:
- Must verify whether Tommy Tuberville filed for Governor.
- Must not include Senate-only candidates in the governor roster.
- Must identify the official Republican gubernatorial nominee if the primary
  has concluded.
```

Each phase should restate the relevant goal fragment:

- Discovery: candidate/roster constraints.
- Finance and issues: target candidates only after roster is confirmed.
- Forecast: constraints around unresolved nominees and placeholders.
- Review: explicit questions the reviewer must answer.

### Acceptance Criteria

- Logs show the interpreted correction constraints early in the run.
- Review output explicitly addresses whether the correction goal was satisfied.
- A targeted correction run does not spend most of its budget re-researching
  unrelated profile details before resolving the stated problem.

## Phase 5: Source Playbooks by Race Type

Status: Implemented.

### Problem

The same generic discovery approach is used for all offices. Source reliability
varies by race type.

### Implementation

Define prompt playbooks:

| Race Type | Preferred Sources |
| --- | --- |
| Federal House/Senate | State filing list, state official results, FEC election/candidate pages, House/Senate incumbent bios, Ballotpedia/Wikipedia as secondary |
| Governor/statewide | State election authority, state campaign finance, official campaign sites, local/state news, Ballotpedia as secondary |
| State legislative/local | State/local election authority, local news, campaign sites, Ballotpedia when available |
| Top-two/top-four/RCV | Official election rules and advancement list first, then candidate sources |
| Uncontested | Official ballot/filing proof that no opponent filed |

### Acceptance Criteria

- The agent chooses queries and source order based on office type.
- Federal races no longer overuse FEC as if filing equals nomination.
- Statewide races no longer import federal candidates because FEC/search pages
  are easier to find.

## Phase 6: Review Specialization

Status: Implemented.

### Problem

General review tends to reward source density and neutral prose. It can miss
the highest-impact error: the roster itself is wrong.

### Implementation

Keep existing reviewers, but add role framing inside prompts:

- Roster auditor: exact office, candidate provenance, primary/general stage,
  missing major-party candidate, wrong-office contamination.
- Source auditor: source accessibility, stale sources, whether cited source
  supports the specific claim.
- Editorial auditor: neutral wording, asymmetric framing, readability.

This can be done through prompt structure without changing providers.

### Acceptance Criteria

- Reviews contain a clear roster audit section.
- A wrong-office candidate receives an error even if their bio is credible.
- Missing or unresolved nominees are surfaced as uncertainty, not silently
  approved.

## Phase 7: Post-Run Audit Notes

Status: Implemented.

### Problem

Admins need a fast way to understand what a run changed and what uncertainty
remains without reading all logs.

### Implementation

At the end of a run, produce a deterministic or lightweight note:

```json
{
  "run_audit": {
    "roster_source_summary": "Official PA candidate filing list plus local news",
    "contest_stage": "post_primary_general",
    "candidate_changes": ["Removed primary loser X", "Added nominee Y"],
    "forecast_changes": ["Changed from likely R to tossup"],
    "remaining_uncertainty": ["Only one partisan poll available"],
    "publish_attention": ["New draft differs from published roster"]
  }
}
```

This is not a publish block. It is a triage aid.

### Acceptance Criteria

- Admin can tell why a draft changed without reading full logs.
- Runs with unresolved roster uncertainty say so plainly.
- Draft/published drift is easy to prioritize.

## Delivered State

All seven phases are implemented in the shared schema, agent prompts and
phase runners, review packet, and admin-visible race output. The current
operational follow-up is data QA: run targeted, evidence-backed refreshes for
races whose published data is stale or uncertain, review the generated draft,
and publish only after validation passes. That work is intentionally not
automated because it consumes external API budget and changes public data.

## Historical Implementation Order

1. Finish prompt/process changes already started:
   - race identity date-aware discovery
   - official-source-first roster language
   - placeholder-free forecast language
   - roster-first review framing
2. Add `contest_stage` to shared models and frontend types.
3. Add race identity brief generation and pass it into downstream prompts.
4. Add candidate roster provenance.
5. Add contest-stage-specific candidate inclusion instructions.
6. Add correction-goal decomposition and review confirmation.
7. Add role-framed review sections.
8. Add post-run audit notes.

## Suggested Tests

- Alabama governor: ensure Senate candidates are not included unless sourced as
  governor candidates.
- PA-08 style post-primary House race: ensure primary losers are excluded and
  nominees are retained.
- Alaska Senate/top-four/RCV: ensure a crowded valid field is not reduced to a
  two-party race prematurely.
- Unresolved primary: ensure forecast is party-level and does not invent
  `Republican Candidate`.
- Ballotpedia blocked: ensure prompts direct the agent to official/FEC/news
  sources instead of repeated blocked fetches.
- Correction goal: ensure the run prompt and review prompt preserve the stated
  correction constraints.

## Non-Goals

- Do not create separate public primary pages in this phase.
- Do not automatically publish corrected drafts.
- Do not add hard publish gates as the main mechanism for quality improvement.
- Do not replace the existing three-reviewer model solely for this work.
- Do not change the twelve canonical issue names.
