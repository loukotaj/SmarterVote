# Senate Forecast Recovery Handoff

Date: 2026-06-22

## Current State

Frontend and narrative code changes were committed and pushed to `main`. CI and infrastructure deploy passed after the fixes.

Commits pushed:

- `24189f5` - Improve forecast page layout and narratives
- `e35142d` - Generate static chamber narratives with OpenRouter
- `410b60d` - Format forecast page
- `760ebc5` - Derive missing forecast win probability

Local worktree was clean when this handoff was written.

## What Was Changed in Code

- Forecast page layout:
  - Map/stat grid stretches vertically.
  - Forecast ratings breakdown moved to full-width.
  - House map coloring now uses House race forecast ratings, not only Senate coloring.
  - House map tooltips summarize forecasted races.
- Forecast narratives:
  - Static chamber fallback narratives now name competitive races instead of generic copy.
  - Static forecast publishing script can generate chamber narratives through OpenRouter.
  - Admin chamber prompt was improved, though the production endpoint already had OpenRouter support.
- Race forecast persistence:
  - `set_forecast` now persists `takeaway`, `key_reasons`, and `uncertainty`.
  - If `win_probability` is missing but `party_probabilities` contains the predicted party, it derives `win_probability`.

## Validation Already Run

- Python targeted tests passed:
  - `tests/test_forecast_summary.py`
  - `tests/test_editing_tools.py`
  - `tests/test_chamber_narratives.py`
- Frontend checks passed:
  - `npm run check`
  - `npm run build`
  - `npm run test:unit -- --run`
  - `npm run lint`
- GitHub CI passed on final commit.
- Infrastructure deploy passed.

## Pipeline Actions Taken

Georgia pilot:

- Queued `ga-senate-2026` for `discovery,polling,forecast`.
- It completed cheaply, about `$0.041`.
- Forecast-only rerun after deploy produced a valid draft:
  - Democratic
  - `0.68`
  - `lean_d`

Senate-wide run:

- `audit_senate_forecast_data` showed 32 stale Senate races.
- Queued 32 stale Senate races for `discovery,polling,forecast`, `cheap_mode:false`, `model_profile:"quality"`.
- Most completed, but some failed or produced bad drafts.

Problem runs/drafts observed:

- `ut-senate-2026`: failed during discovery with empty/missing candidates save guard.
- `nc-senate-2026`: run marked failed by stale recheck even though it had a usable draft forecast.
- `sd-senate-2026`: run marked failed by stale recheck even though it had a usable draft forecast.
- `me-senate-2026`: initial draft forecast had null winner/probability; later cleanup rerun regressed the draft to thin data and `lean_r`.
- `mi-senate-2026`: draft forecast remained null winner/probability.
- `mn-senate-2026`: draft had incomplete candidate/profile data and `rating:"other"`.

## Important Mistake / Risk

I queued cleanup reruns with `force_fresh:true` for:

- `me-senate-2026`
- `mi-senate-2026`
- `ut-senate-2026`
- `nc-senate-2026`
- `sd-senate-2026`

This was wrong for a cleanup forecast-only rerun. With `force_fresh:true`, the runner attempted discovery refresh behavior and some races hit the empty-candidates draft save guard. Maine completed but regressed its draft to thin race data with no issue/career/donor detail and a low-confidence forecast.

Known high-risk draft after this:

- `me-senate-2026` draft is likely worse than the published version and should not be published.

Likely still-bad drafts:

- `mi-senate-2026`
- `mn-senate-2026`
- `ut-senate-2026`

## Publish Actions Taken

After the failed cleanup, I published only Senate drafts that appeared to have sane forecast fields and skipped `me`, `mi`, `mn`, and `ut`.

Published successfully:

- `ar-senate-2026`
- `co-senate-2026`
- `fl-senate-2026-special`
- `ga-senate-2026`
- `il-senate-2026`
- `nc-senate-2026`
- `nh-senate-2026`
- `oh-senate-2026-special`
- `sc-senate-2026`
- `sd-senate-2026`
- `tn-senate-2026`
- `tx-senate-2026`
- `wv-senate-2026`

Publish was rejected for these because drafts were operationally incomplete with remaining `review` step:

- `ak-senate-2026`
- `al-senate-2026`
- `de-senate-2026`
- `ia-senate-2026`
- `la-senate-2026`
- `ma-senate-2026`
- `ms-senate-2026`
- `mt-senate-2026`
- `ne-senate-2026`
- `nj-senate-2026`
- `nm-senate-2026`
- `ok-senate-2026`
- `or-senate-2026`
- `ri-senate-2026`
- `va-senate-2026`
- `wv-senate-2026`

Note: `wv-senate-2026` appeared in both the successful publish list and the rejected list from tool output. Treat that as needing verification.

## Chamber Forecasts

Do not trust chamber forecast state yet.

- A previous `generate_chamber_forecasts` call errored with a races-api 500.
- A dry-run static bundle succeeded, but that was before publishing drafts and did not solve the OpenRouter/admin endpoint issue.
- Chamber forecasts should be generated only after published race data is repaired/audited.

## Recommended Recovery Plan

1. Stop queue activity.
   - Confirm no active queue items before doing anything else.

2. Protect published data.
   - Do not publish any remaining Senate drafts yet.
   - Do not run chamber forecast generation yet.

3. Audit the 13 races that were published.
   - Compare current published JSON against previous GCS object versions or other backups if available.
   - Specifically verify candidates, issues, summaries, donor/voting fields, polling, and forecast.
   - If any published race lost profile richness due to the full Senate run, restore from backup or rerun full quality pipeline.

4. Delete or quarantine bad drafts.
   - Delete drafts for `me-senate-2026`, `mi-senate-2026`, `mn-senate-2026`, and `ut-senate-2026` if published data is better.
   - Consider deleting any draft that has null forecast winner/probability, `rating:"other"`, empty issues, or empty candidate summaries.

5. Full reruns likely needed.
   - For every successfully published race listed above, consider full `discovery,polling,forecast,review` reruns if the published data lacks prior A-grade issue/profile depth.
   - Do not use `force_fresh:true` for a simple forecast cleanup unless the goal is explicitly to rebuild discovery data.

6. Fix pipeline behavior before another batch.
   - Forecast-only reruns should not refresh discovery or overwrite candidate/profile data.
   - Add a guard that refuses to save a draft if it would replace a richer race with a thinner one.
   - Add a publish guard for forecast completeness and profile completeness, not only operational step state.

7. After race data is repaired:
   - Publish all known-good Senate race drafts.
   - Generate chamber forecasts using the OpenRouter-backed endpoint.
   - If the endpoint still 500s, debug that endpoint before publishing chamber summaries.
   - Audit chamber forecast drafts before publishing them.

## Suggested Immediate Commands / Checks

Use MCP/admin tools, but mutation-free first:

- Check active queue.
- Review unpublished drafts.
- Fetch current published and draft data for the 13 published races.
- Compare candidate counts and issue completeness.
- Verify whether GCS object versioning or backups can restore pre-publish versions.

Highest-priority race checks:

- `me-senate-2026`: bad draft should be removed or overwritten from good published data.
- `mn-senate-2026`: incomplete draft should not be published.
- `mi-senate-2026`: null forecast draft should not be published.
- `ut-senate-2026`: failed/no usable draft.
- `wv-senate-2026`: verify publish state because tool output was contradictory.
