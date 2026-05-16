import type { EntryGenerator, PageLoad } from "./$types";
import { candidateEntries, fetchPublishedRace } from "$lib/prerenderData";

export const prerender = true;

export const entries: EntryGenerator = async () => candidateEntries();

export const load: PageLoad = async ({ params, fetch }) => {
  return {
    prerenderedRace: await fetchPublishedRace(params.slug, fetch),
  };
};
