import type { LayoutLoad } from "./$types";
import { getRaceSummaries } from "$lib/api";

export const trailingSlash = "always";

export const prerender = true;

export const load: LayoutLoad = async ({ fetch }) => {
  try {
    const races = await getRaceSummaries(fetch);
    return { races };
  } catch (error) {
    console.error("Failed to load race summaries in layout load function:", error);
    return { races: [] };
  }
};
