import type { PageLoad } from "./$types";
import { nationalElectionRaces } from "$lib/utils/homepage";

export const load: PageLoad = async ({ parent }) => {
  const { races = [] } = await parent();
  return { races: nationalElectionRaces(races) };
};
