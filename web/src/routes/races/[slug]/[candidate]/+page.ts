import type { EntryGenerator, PageLoad } from "./$types";
import { candidateEntries, fetchPublishedRace } from "$lib/prerenderData";

export const prerender = true;

export const entries: EntryGenerator = async () => candidateEntries();

export const load: PageLoad = async ({ params, fetch }) => {
  try {
    return {
      prerenderedRace: await fetchPublishedRace(params.slug, fetch),
    };
  } catch (error) {
    console.error(
      `Failed to load prerendered race ${params.slug} for candidate:`,
      error,
    );
    return {
      prerenderedRace: null,
    };
  }
};
