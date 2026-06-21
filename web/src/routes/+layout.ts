import type { LayoutLoad } from "./$types";
import { getRaceSummaries } from "$lib/api";
import type { RaceSummary } from "$lib/types";

export const trailingSlash = "always";

export const prerender = true;

export const load: LayoutLoad = async ({ fetch }) => {
  try {
    const races = await getRaceSummaries(fetch);
    return { races };
  } catch {
    // Keep the shell renderable when local fast builds do not have an API or GCS data URL.
    return { races: [] as RaceSummary[] };
  }
};
