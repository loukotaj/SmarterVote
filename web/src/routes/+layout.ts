import type { LayoutLoad } from "./$types";
import { getRaceSummaries } from "$lib/api";
import type { RaceSummary } from "$lib/types";

export const trailingSlash = "always";

export const prerender = true;

export const load: LayoutLoad = async ({ fetch }) => {
  try {
    const races = await getRaceSummaries(fetch);
    return { races };
  } catch (error) {
    console.error("Failed to load layout data in layout load function:", error);
    let races: RaceSummary[] = [];
    try {
      races = await getRaceSummaries(fetch);
    } catch (_) {
      // Keep the shell renderable when the API is unavailable.
    }
    return { races };
  }
};
