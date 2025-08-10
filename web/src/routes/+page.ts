import { getRaceSummaries } from "$lib/api";
import type { PageLoad } from "./$types";

export const load: PageLoad = async ({ fetch }) => {
  try {
    const races = await getRaceSummaries(fetch);
    return {
      races
    };
  } catch (error) {
    console.error("Failed to load race summaries:", error);
    return {
      races: []
    };
  }
};
