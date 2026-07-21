import type { PageLoad } from "./$types";
import { loadPrerenderSummaries } from "$lib/prerenderData";
import type { RaceSummary } from "$lib/types";
import {
  gradeAHomepageFallbacks,
  gradeAHomepageRaceIds,
  isGradeAHomepageRace,
  mergeGradeAHomepageRaces,
} from "$lib/homepagePreview";
import { loadPrerenderRace } from "$lib/prerenderData";
import {
  homepageMetrics,
  nationalElectionRaces,
  recentlyUpdated,
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
  let gradeARaces = gradeAHomepageFallbacks;
  const indexedGradeAIds = recentlyUpdated(
    nationalRaces.filter((race) => race.quality_grade === "A"),
    5,
  ).map((race) => race.id);
  const previewIds = [
    ...new Set([...indexedGradeAIds, ...gradeAHomepageRaceIds]),
  ];

  // Production syncs published race JSON into static/ before prerendering. Try
  // those local files even when VITE_PUBLIC_DATA_URL is unset; fast local/CI
  // builds can still fall back when the per-race fixtures are unavailable.
  const published = await Promise.allSettled(
    previewIds.map((id) => loadPrerenderRace(id, fetch)),
  );
  const verified = published
    .filter(
      (
        result,
      ): result is PromiseFulfilledResult<(typeof gradeARaces)[number]> =>
        result.status === "fulfilled" && isGradeAHomepageRace(result.value),
    )
    .map((result) => result.value);
  gradeARaces = mergeGradeAHomepageRaces(verified);

  // The editorial list is intentionally manual and independent of update time.
  // Missing or unpublished races are skipped without changing the chosen order.
  const featuredRaces = selectFeaturedRaces(nationalRaces);

  return {
    featuredRaces,
    gradeARaces,
    metrics: homepageMetrics(nationalRaces, new Date().toISOString()),
  };
};
