import type { PageLoad } from "./$types";
import { getRace } from "$lib/api";
import { publicDataBase } from "$lib/config/api";
import type { Race } from "$lib/types";
import {
  homepageMetrics,
  isPreviewEligible,
  nationalElectionRaces,
  recentlyUpdated,
} from "$lib/utils/homepage";

export const load: PageLoad = async ({ fetch, parent }) => {
  const { races = [] } = await parent();
  const nationalRaces = nationalElectionRaces(races);
  const featuredRaces = recentlyUpdated(nationalRaces, 6);
  let preview: Race | null = null;

  // Fast local/CI builds only include summaries.json. Avoid making the prerenderer
  // crawl missing per-race JSON; production supplies the published GCS data base.
  if (publicDataBase()) {
    for (const summary of recentlyUpdated(nationalRaces, 12)) {
      try {
        const candidate = await getRace(summary.id, fetch, false);
        if (isPreviewEligible(candidate)) {
          preview = candidate;
          break;
        }
      } catch {
        // A preview is optional; individual unavailable records must not block the page.
      }
    }
  }

  return {
    nationalRaces,
    featuredRaces,
    preview,
    metrics: homepageMetrics(nationalRaces, new Date().toISOString()),
  };
};
