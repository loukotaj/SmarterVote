import type { PageLoad } from "./$types";
import { loadPrerenderSummaries } from "$lib/prerenderData";
import type { Race, RaceSummary } from "$lib/types";
import {
  isHomepagePreviewRace,
  mergeHomepagePreviewRaces,
} from "$lib/homepagePreview";
import { loadPrerenderRace } from "$lib/prerenderData";
import {
  featuredHomepageRaceIds,
  homepageMetrics,
  nationalElectionRaces,
  selectFeaturedRaces,
} from "$lib/utils/homepage";

export const load: PageLoad = async ({ fetch }) => {
  let races: RaceSummary[] = [];
  try {
    races = await loadPrerenderSummaries(fetch);
  } catch {
    // Keep the homepage renderable in fast local builds without published data.
  }
  const nationalRaces = nationalElectionRaces(races);

  // The top comparison and editorial section share one explicit race order.
  // Production syncs these published race files into static/ before prerendering.
  const published = await Promise.allSettled(
    featuredHomepageRaceIds.map((id) => loadPrerenderRace(id, fetch)),
  );
  const previewRaces = mergeHomepagePreviewRaces(
    published
      .filter(
        (result): result is PromiseFulfilledResult<Race> =>
          result.status === "fulfilled" && isHomepagePreviewRace(result.value),
      )
      .map((result) => result.value),
  );

  // The editorial list is intentionally manual and independent of update time.
  // Missing or unpublished races are skipped without changing the chosen order.
  const featuredRaces = selectFeaturedRaces(nationalRaces);

  return {
    featuredRaces,
    gradeARaces: previewRaces,
    metrics: homepageMetrics(nationalRaces, new Date().toISOString()),
  };
};
