import type { EntryGenerator, PageLoad } from "./$types";
import { fetchPublishedRace, raceEntries } from "$lib/prerenderData";

export const prerender = true;

export const entries: EntryGenerator = async () => raceEntries();

export const load: PageLoad = async ({ params, fetch }) => {
  return {
    prerenderedRace: await fetchPublishedRace(params.slug, fetch),
  };
};
