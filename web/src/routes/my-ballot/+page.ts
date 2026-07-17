import type { PageLoad } from "./$types";
import { loadPrerenderSummaries } from "$lib/prerenderData";
import type { RaceSummary } from "$lib/types";
import { nationalElectionRaces } from "$lib/utils/homepage";
import { toDirectoryRaceSummaries } from "$lib/utils/publicRaceSummaries";

export const load: PageLoad = async ({ fetch }) => {
  let races: RaceSummary[] = [];
  try {
    races = await loadPrerenderSummaries(fetch);
  } catch {
    // Keep ballot lookup renderable in fast local builds without published data.
  }
  return { races: toDirectoryRaceSummaries(nationalElectionRaces(races)) };
};
