# Senate Forecast Page Refinement Plan

## Goal

Make the Senate forecast page feel like a real published forecast product, not a generic race browser.

The Senate tab should display a coherent chamber-level projection from static published forecast data, then let users inspect the races driving that projection. The public page should not depend on browser API calls for forecast summary data.

## Current Problems To Fix

- The deployed page can display a narrative that says Republican control is projected while the control widget says `No clear control`.
- Chamber-level probabilities are not visible enough, so users cannot see how likely each control outcome is.
- The current narrative is mechanically correct but not compelling as an outlook or analysis.
- Race cards waste horizontal space and can truncate projected winner names.
- The expand-analysis button behavior has been fragile.
- The map is not yet carrying enough forecast meaning.
- The data pipeline is under-specified: final publish needs to define when to rerun Senate race forecasts, when to regenerate chamber forecasts, and which MCP tools perform each step.

## Product Principles

- The published chamber projection is the source of truth for chamber control.
- A 50-50 Senate is Republican control when the VP tie-break assumption is Republican.
- The UI should display the forecast call, probabilities, seat math, and uncertainty together.
- Race cards should be dense enough to scan and wide enough to avoid truncating important names.
- The map should become a useful forecast surface, not a decorative one.
- Publishing should be repeatable through MCP tools, with validation before anything goes live.

## Static Data Model

Use a published static projection payload as the source of truth for the Senate tab.

Required chamber-level fields:

- `schema_version`
- `control_party`
- `control_probability`
- `outcome_probabilities`
  - `Democratic`
  - `Republican`
  - `tie_50_50`
  - optional `Other`
- `projected_seats`
  - Democratic
  - Republican
  - Other
- `expected_seats`
  - Democratic
  - Republican
  - Other
- `seat_distribution`
  - probability by final Senate split, for example `51R-49D`, `50R-50D`, `51D-49R`
- `tossup_count`
- `competitive_race_count`
- `key_races`
  - race id
  - state
  - projected winner
  - party
  - win probability
  - rating
  - seat impact
- `narrative`
- `bottom_line`
- `why_party_favored`
- `opposing_party_path`
- `key_uncertainty`
- `updated_at`
- `method`
- `source_summary_hash`
- `source_race_count`
- `senate_forecast_count`
- `vp_tiebreak_party`

The current `chamber_forecasts.v2` shape is a good start, but it should be expanded to include structured analysis fields and a real seat distribution.

Data contract rules:

- `control_party` is authoritative for the control label.
- `control_probability` is the displayed headline probability for `control_party`.
- `outcome_probabilities.Republican` must include the `tie_50_50` probability when the VP assumption is Republican.
- `projected_seats` is allowed to be 50 Democratic and 50 Republican, but the UI must still show Republican control if `control_party` is Republican.
- `seat_distribution` should sum to approximately 1.0.
- Senate projections must account for holdover seats plus active 2026 races, with no double-counting active states.
- Static validation should fail if `source_race_count` and `senate_forecast_count` disagree for published U.S. Senate summaries.

## Above-The-Fold Layout

### Forecast Header

Replace the generic analysis card with a compact forecast header.

Display:

- `2026 Senate Forecast`
- Status badge: `Republican control projected`
- Updated date
- Method note: `Static published SmarterVote projection`
- VP tie-break note when applicable

The header should immediately answer: who is projected to control the chamber?

### Control Probability Panel

Add a prominent control probability module.

Example:

```text
Republican control
63%

Democratic control
37%

50-50 VP tie-break scenario
6%
```

This should be visual:

- segmented probability bar
- party colors
- tie-break segment clearly labeled
- tooltip or note explaining that the tie-break segment is included in Republican control
- short text callout, for example: `Republicans are favored because 50-50 outcomes are counted as Republican control under the VP tie-break assumption.`

### Seats Projection Bar

Use the published projection data directly.

Display:

```text
Projected seats
Democratic 50 | Republican 50

Expected seats
Democratic 49.1 | Republican 50.3 | Other 0.5
```

The seat bar should include:

- 100-seat scale
- 51-seat majority marker
- 50-50 tie marker
- VP tie-break annotation when projected seats are 50-50

Do not show a 50-50 projection as `No clear control`. The display call comes from the published chamber forecast.

### Data Consistency Guard

If the static payload has a chamber forecast, the page must not use fallback aggregate logic for:

- control label
- control probability
- projected seats
- expected seats
- toss-up count
- competitive race count
- narrative

Fallback aggregate logic is only for missing or invalid static chamber forecast payloads.

## Outlook And Analysis

Replace the single generated paragraph with structured published analysis.

Sections:

- `Bottom line`
- `Why Republicans are favored`
- `Democratic path`
- `Key uncertainty`
- `Races that matter most`

Example:

```text
Bottom line
Republicans are favored to control the Senate because the model projects an even 50-50 seat split and counts that as Republican control under the VP tie-break assumption.

Why Republicans are favored
The chamber forecast gives Republicans a 63% control probability after combining race-level probabilities, holdover seats, and the tie-break scenario.

Democratic path
Democrats need to outperform in the toss-up group and convert at least one Republican-leaning competitive race.

Key uncertainty
The forecast depends heavily on a small group of early-cycle races where polling remains limited or volatile.
```

This should be generated and stored in the static chamber payload, not improvised in the UI. The generated text should include concrete numbers from the payload. Avoid bland sentences like `the model identifies competitive races` unless paired with the actual probability and seat math.

## Race Cards

### Layout

Use more horizontal space.

Responsive grid:

- desktop wide: 3 cards per row where cards remain readable
- desktop/tablet: 2 cards per row
- mobile: 1 card per row

The Senate tab has a manageable number of races, so a multi-column grid will make scanning much better. Cards should avoid nested-card styling. Use one clear card per race with dense internal rows.

### Card Anatomy

Each card should show:

- State / race title
- Rating badge
- Projected winner, wrapping instead of truncating
- Win probability
- Democratic / Republican probability split
- Estimated margin
- Poll count
- state importance / control impact when available
- One-sentence takeaway
- Expand button for full analysis

Example:

```text
Georgia Senate
Tilt D

Projected winner
Jon Ossoff
61%

D 61% | R 39%
Margin: D +3.0
Polls: 1

Takeaway...
[Expand analysis]
```

### Expand Analysis Drawer

The drawer should include:

- full rationale
- key reasons
- uncertainty
- source links
- polling basis
- generated timestamp
- model used

Behavior:

- expansion state persists until the user closes it or changes tabs
- no reactive reset on every render
- the button is a real `type="button"`

## Filters And Sorting

### Default Sort

Default sort should be by control relevance, not just competitiveness.

Initial ranking formula:

- closeness to 50%
- race rating group
- whether the race changes the chamber projection
- whether the race appears in `key_races`

If the chamber payload provides `key_races`, use that order first. Otherwise derive control relevance locally from rating and win probability.

### Sort Options

- `Most likely to decide control`
- `Most competitive`
- `Highest Democratic pickup chance`
- `Highest Republican hold/pickup chance`
- `Rating`
- `State`

### Filters

Use compact pills:

- All
- Toss-ups
- Tilt
- Lean
- Likely/Safe
- Democratic projected
- Republican projected

## Map Improvements

The Senate map should explain the forecast.

Required behavior:

- Color states by forecast rating.
- Distinguish active 2026 races from holdover states.
- Make active 2026 states visually stronger than holdovers.
- Show tooltip details:
  - projected winner
  - party
  - win probability
  - rating
  - active race versus holdover
  - if holdover, number of seats and party
- Support selected-state filtering without breaking layout.
- Use the same published static forecast data as the card grid.
- Provide a visible legend for active races, holdovers, and rating intensity.
- Preserve keyboard/mouse accessibility for state selection.

Implementation notes:

- Active Senate races should override holdover coloring for that state.
- States with two holdover seats should still communicate both seats in the tooltip.
- Toss-up and tilt states should be visually prominent.
- The map and cards should agree on race counts and ratings.
- Map state should be derived from a single helper shared with the cards to avoid divergent coloring.

## Static Build Requirements

The public forecast page should use static data.

Default bundled data:

- `data/published/summaries.json`
- `data/published/chamber_forecasts.json`

Allowed runtime fetch mode:

- If `VITE_PUBLIC_DATA_URL` is explicitly configured, fetch static JSON from that static bucket path.

Not allowed for the public forecast page:

- Runtime browser call to `/races/chamber_forecasts`
- Runtime browser call to `/races/summaries`

Admin tools can still call APIs. The public forecast tab should not. This requirement applies after hydration too. The initial HTML and client-side navigation should both work from static data.

## Data Pipeline And Final Publish Flow

The final publish should be a repeatable data operation, not a manual JSON edit.

Current assumption: the existing published Senate forecasts are not automatically "ready." Treat them as ready only after `audit_senate_forecast_data` verifies completeness and freshness. The expected steady-state path is audit first, targeted reruns only where the audit shows missing/stale/low-quality forecast inputs, then chamber forecast generation from the reviewed published race forecasts.

Recommended sequence:

1. Identify all published U.S. Senate races.
2. Audit which Senate races have complete race-level forecasts.
3. Decide which Senate races need forecast reruns.
   - Missing forecast: rerun.
   - Forecast generated before the latest candidate/polling refresh: rerun.
   - Forecast confidence is low because of missing polling but the race is safe/likely by fundamentals: rerun only if source data changed.
   - Forecast exists and source race data is fresh: do not rerun just to churn output.
4. Rerun the `forecast` pipeline step for selected Senate races.
   - Prefer targeted forecast-only reruns over full pipeline reruns unless candidate data, polling, or sources are stale.
   - Use full pipeline reruns only for races with incomplete candidate data, stale polling, or missing source support.
5. Review generated race-level forecast fields:
   - predicted winner
   - predicted party
   - win probability
   - party probabilities
   - margin estimate
   - rating
   - takeaway
   - key reasons
   - uncertainty
6. Publish updated Senate race drafts only after review.
7. Refresh static `summaries.json` from published race records.
8. Hydrate summary forecasts from full published race records when the summary index lags.
9. Generate the chamber forecast payload from static summaries.
10. Validate the chamber payload:
   - all Senate summaries have forecasts
   - projected Senate seats sum to 100
   - 50-50 counts as Republican control
   - control probabilities are present
   - seat distribution is present
   - top key races are present
   - narrative references the same control party as `control_party`
   - `control_probability` matches `outcome_probabilities[control_party]`
   - no active Senate race is counted twice with holdovers
11. Publish static chamber forecast data.
12. Run local validation.
13. Push code and checked-in static data changes.
14. Monitor CI until all required checks pass.
15. Deploy from the verified commit after CI is green.
16. Run automated live/static verification.
17. Perform manual human verification:
   - no browser API call to races API forecast endpoints
   - projected control agrees with narrative
   - probability panel agrees with published payload
   - race cards and map agree with static data

### Publish Artifacts

Final publish should produce or update:

- Published Senate RaceJSON files for races that were rerun and reviewed.
- `data/published/summaries.json`
- `data/published/chamber_forecasts.json`
- Static web build output deployed to Cloudflare Pages.

The chamber forecast should be regenerated after race forecast publication, not before. Otherwise the chamber call can be built from stale race-level probabilities.

## MCP Tooling Needed

Existing useful tools:

- `health`
- `list_published_races`
- `list_race_summaries`
- `get_published_race`
- `get_race_record`
- `list_unpublished_drafts`
- `publish_race`
- `publish_races`
- `queue_races`
- `get_run`
- `get_run_logs`
- `list_active_runs`
- `clear_races_api_cache`
- `trigger_web_deploy`

Tools already added or planned in this work should be formalized and exposed in the installed MCP server:

- `refresh_static_race_summaries`
  - Fetch published summaries and write `data/published/summaries.json`.
  - Hydrate missing Senate forecast summaries from full published RaceJSON records.

- `generate_static_chamber_forecasts`
  - Generate `data/published/chamber_forecasts.json` from static summaries.
  - Should not publish by itself.

- `refresh_static_forecast_data`
  - Run summary refresh and chamber forecast generation together.

- `publish_static_chamber_forecasts`
  - Publish the structured chamber forecast payload to the races API/GCS storage.

Additional MCP tools needed:

- `audit_senate_forecast_data`
  - Return Senate race count, forecast count, missing forecast race ids, stale forecast race ids, projected control, expected seats, and top competitive races.

- `queue_senate_forecast_reruns`
  - Queue only the forecast step for selected Senate races.
  - Should accept `race_ids`, `force_fresh`, `model_profile`, and `note`.
  - Should default to draft-only output.
  - Should return run ids for monitoring.

- `monitor_senate_forecast_reruns`
  - Poll selected run ids.
  - Return completed, failed, and still-running ids.
  - Surface forecast-step errors directly.

- `review_senate_forecast_drafts`
  - Summarize forecast changes before publish.
  - Show old published forecast versus new draft forecast.
  - Flag large probability/rating swings.

- `validate_static_chamber_forecasts`
  - Validate local static chamber forecast JSON before publish.
  - Should fail loudly on missing Senate forecasts, invalid probabilities, missing seat distribution, or 50-50 control mishandling.

- `publish_static_forecast_bundle`
  - Publish both refreshed summaries and chamber forecasts as a coherent static bundle.
  - Should include a dry-run mode.

- `verify_live_forecast_page_data`
  - Check live static/public endpoints and report whether the browser should have everything it needs without races API calls.

Tooling safeguards:

- No tool should publish race data unless explicitly requested.
- Generation tools should support dry-run output.
- Publish tools should report exact race ids and artifact paths.
- Validation tools should fail closed; warning-only validation is not enough for chamber control math.

## Testing Plan

### Data Pipeline Test Run

Before treating the page as ready, run the forecast data pipeline through MCP in dry-run or review mode.

Required MCP checks:

1. `health`
   - Confirm the races API is reachable.
2. `audit_senate_forecast_data`
   - Confirm all published U.S. Senate races are included.
   - Confirm every Senate race has a forecast.
   - Report stale forecasts, missing forecasts, incomplete party probabilities, and low-quality forecast inputs.
3. `queue_senate_forecast_reruns`
   - Run only if the audit reports missing or stale Senate race forecasts.
   - Prefer forecast-only reruns.
   - Return run ids.
4. `monitor_senate_forecast_reruns`
   - Wait for all reruns to complete.
   - Fail the test run if any rerun fails.
5. `review_senate_forecast_drafts`
   - Compare new draft forecasts against published forecasts.
   - Flag large changes before publish.
6. `publish_race` or `publish_races`
   - Run only after the draft review is acceptable and publish is explicitly intended.
7. `refresh_static_forecast_data`
   - Refresh local static summaries.
   - Hydrate summary forecast gaps from full published race records.
   - Regenerate chamber forecasts locally.
8. `validate_static_chamber_forecasts`
   - Confirm projected Senate seats sum to 100.
   - Confirm 50-50 Senate maps to Republican control when `vp_tiebreak_party` is Republican.
   - Confirm control probabilities, expected seats, seat distribution, key races, and structured analysis fields exist.
9. `publish_static_forecast_bundle` or `publish_static_chamber_forecasts`
   - Dry-run first.
   - Publish only after validation succeeds.
10. `verify_live_forecast_page_data`
   - Confirm live/static forecast data is available for the deployed page.
   - Confirm no browser races API calls are required for the forecast tab.

If no Senate race forecasts are stale or missing, record the audit output and skip reruns. Do not rerun forecasts just to churn model outputs.

Senate forecast rerun policy:

- Rerun Senate forecasts before final publish when the audit reports missing forecast fields, stale generated timestamps, changed source race data, incomplete party probabilities, or missing narrative fields used by the redesigned cards.
- Do not assume the currently published forecasts are ready until the audit proves they are complete, fresh, and internally consistent.
- If the audit is clean, keep the published race forecasts and regenerate only the static summaries and chamber forecast payload from those published records.
- If any forecast rerun produces a draft with a large rating or probability swing, require draft review before publishing that race update.

Automated tests:

- 50-50 Senate counts as Republican control.
- Forecast page uses static bundled data by default.
- No default browser fetch for `summaries.json` or `chamber_forecasts.json`.
- Chamber projection contains Senate control probability.
- Chamber projection contains seat distribution.
- Static refresh hydrates missing Senate forecast summaries.
- Expanded race analysis state is not immediately reset.
- Projected winner names are allowed to wrap.
- Static chamber forecast validation rejects missing `seat_distribution`.
- Static chamber forecast validation rejects Senate 50-50 with `control_party: Other`.
- Senate map helper produces the same rating group as the cards.

Local validation commands:

- `PYTHONPATH=. python -m pytest tests/test_forecast_summary.py -v`
- `cd web && npm run check`
- `cd web && npm run build`
- `cd web && npm run test:unit -- --run`

PR / CI validation:

- Push the branch after local validation passes.
- Monitor GitHub checks until all required jobs pass.
- Required checks:
  - Secret Scan
  - Test API Services
  - Test Agent Cloud Function
  - Test Pipeline
  - Test Web Frontend
  - Validate Terraform
  - CI Summary
- Do not move to manual live verification until CI is green.

Deploy and automated live verification:

- Deploy only from the commit that passed CI.
- Use `trigger_web_deploy` or the Cloudflare Pages workflow if deployment is not automatic for the verified commit.
- Run `verify_live_forecast_page_data` after deploy completes.
- Confirm the live static artifacts contain the same `source_summary_hash`, `updated_at`, projected control, and probability fields validated locally.
- Confirm network behavior with an automated browser check before manual QA:
  - page loads `/forecast/?tab=senate`
  - no calls to `/races/summaries`
  - no calls to `/races/chamber_forecasts`
  - no calls to races API endpoints for public forecast data
  - static bundled data or static bucket JSON is sufficient for the page to render

Manual QA:

- Open `/forecast/?tab=senate`.
- Confirm projected control says `Republican control projected`.
- Confirm narrative and control panel agree.
- Confirm probability panel displays Republican and Democratic control probabilities.
- Confirm 50-50 tie-break is explicitly explained.
- Confirm projected winner names are not truncated.
- Confirm expand analysis opens and stays open.
- Confirm cards use multiple columns on desktop.
- Confirm map colors and tooltips match card data.
- Confirm no browser calls to `/races/chamber_forecasts`.
- Confirm no browser calls to `/races/summaries`.

## Priority Order

1. Fix projected control source of truth.
   - Use published chamber forecast `control_party` whenever available.
   - Never derive `No clear control` from 50-50 Senate seat math.

2. Add chamber probability and seat projection modules.
   - Display control probabilities, expected seats, projected seats, and tie-break probability.

3. Expand chamber forecast payload.
   - Add structured analysis and seat distribution.

4. Redesign Senate race cards.
   - Multi-column grid, better use of space, no winner truncation, richer metrics.

5. Improve expand drawer.
   - Full rationale, reasons, uncertainty, sources, generated metadata.

6. Improve Senate map.
   - Active race coloring, holdover treatment, forecast tooltips, state filtering.

7. Harden MCP pipeline.
   - Audit, rerun, hydrate, generate, validate, publish, verify.

8. Final publish.
   - Rerun stale Senate race forecasts as needed.
   - Publish reviewed race updates.
   - Generate and validate chamber forecast.
   - Deploy the static frontend.
   - Verify live behavior.

## Implementation Phases

### Phase 1: Correctness

- Ensure static chamber forecast controls the displayed Senate control call.
- Remove public forecast-page races API calls.
- Fix expand drawer state.
- Fix projected winner wrapping.

### Phase 2: Data Contract

- Add `seat_distribution`, structured analysis fields, source counts, and source hash to chamber forecasts.
- Add validator for the static forecast payload.
- Add tests for 50-50 control and payload completeness.

### Phase 3: UI Redesign

- Build the forecast header, probability panel, and seat projection bar.
- Redesign Senate race cards into a multi-column scan view.
- Replace one-paragraph narrative with structured outlook sections.

### Phase 4: Map

- Refactor map data preparation into a shared helper.
- Add active race versus holdover treatment.
- Add richer tooltips and legend.
- Verify state selection and responsive layout.

### Phase 5: MCP And Publish

- Add audit, rerun, monitor, validate, publish, and verify MCP tools.
- Run the final data pipeline in dry-run mode.
- Rerun selected Senate race forecasts only if audit says they are stale or missing.
- Publish reviewed race updates.
- Regenerate and publish the chamber forecast.
- Run local validation.
- Push the branch and monitor CI to green.
- Deploy and verify smarter.vote.

## Open Questions

- What exact VP party assumption should be stored for each cycle, and where should it live? This shouldn't be an assumption make it part of generating the forecast and store it with the forecast.
- Should `tie_50_50` be displayed as its own bar segment or as a callout under Republican control?
- What threshold defines a stale race-level forecast: age, changed polling data, changed candidate list, or all three?
- Should chamber forecast narrative be generated by an LLM, templated from structured data, or a hybrid?
- Should Cloudflare deploy bundle checked-in `data/published` only, or should it consume a versioned static data artifact generated during CI?
