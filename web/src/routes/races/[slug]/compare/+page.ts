import type { EntryGenerator, PageLoad } from "./$types";
import { fetchPublishedRace, raceEntries } from "$lib/prerenderData";

export const prerender = true;

export const entries: EntryGenerator = async () => raceEntries();

export const load: PageLoad = async ({ params, fetch }) => {
  try {
    return {
      prerenderedRace: await fetchPublishedRace(params.slug, fetch),
    };
  } catch (error) {
    console.error(`Failed to load prerendered race ${params.slug} for compare:`, error);
    return {
      prerenderedRace: null,
    };
  }
};
