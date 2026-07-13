import type { PageLoad } from "./$types";
import {
  gradeAHomepageFallbacks,
  gradeAHomepageRaceIds,
  isGradeAHomepageRace,
} from "$lib/homepagePreview";
import { loadPrerenderRace } from "$lib/prerenderData";
import type { RaceSummary } from "$lib/types";
import {
  homepageMetrics,
  nationalElectionRaces,
  recentlyUpdated,
} from "$lib/utils/homepage";

export const load: PageLoad = async ({ fetch, parent }) => {
  const { races = [] } = await parent();
  const nationalRaces = nationalElectionRaces(races);
  let gradeARaces = gradeAHomepageFallbacks;
  const indexedGradeAIds = recentlyUpdated(
    nationalRaces.filter((race) => race.quality_grade === "A"),
    5
  ).map((race) => race.id);
  const previewIds = indexedGradeAIds.length
    ? indexedGradeAIds
    : [...gradeAHomepageRaceIds];

  // Production syncs published race JSON into static/ before prerendering. Try
  // those local files even when VITE_PUBLIC_DATA_URL is unset; fast local/CI
  // builds can still fall back when the per-race fixtures are unavailable.
  const published = await Promise.allSettled(
    previewIds.map((id) => loadPrerenderRace(id, fetch))
  );
  const verified = published
    .filter(
      (
        result
      ): result is PromiseFulfilledResult<(typeof gradeARaces)[number]> =>
        result.status === "fulfilled" && isGradeAHomepageRace(result.value)
    )
    .map((result) => result.value);
  if (verified.length) gradeARaces = verified;

  const summaryById = new Map(nationalRaces.map((race) => [race.id, race]));
  const featuredRaces: RaceSummary[] = gradeARaces.map(
    (race) =>
      summaryById.get(race.id) ?? {
        id: race.id,
        title: race.title,
        office: race.office,
        jurisdiction: race.jurisdiction,
        state: race.state,
        contest_stage: race.contest_stage,
        election_date: race.election_date,
        updated_utc: race.updated_utc,
        candidates: race.candidates.map(
          ({ name, party, incumbent, image_url }) => ({
            name,
            party,
            incumbent,
            image_url,
          })
        ),
      }
  );

  return {
    nationalRaces,
    featuredRaces,
    gradeARaces,
    metrics: homepageMetrics(nationalRaces, new Date().toISOString()),
  };
};
