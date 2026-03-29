import { getRaceSummaries } from "$lib/api";
import { logger } from "$lib/utils/logger";
import type { PageLoad } from "./$types";

export const load: PageLoad = async ({ fetch }) => {
  try {
    const races = await getRaceSummaries(fetch);
    return {
      races,
    };
  } catch (error) {
    logger.error("Failed to load race summaries:", error);
    return {
      races: [],
    };
  }
};
