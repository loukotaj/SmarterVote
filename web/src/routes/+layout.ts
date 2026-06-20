import type { LayoutLoad } from "./$types";
import { getRaceSummaries, getChamberForecasts } from "$lib/api";

export const trailingSlash = "always";

export const prerender = true;

export const load: LayoutLoad = async ({ fetch }) => {
  try {
    const [races, chamberForecasts] = await Promise.all([
      getRaceSummaries(fetch),
      getChamberForecasts(fetch),
    ]);
    return { races, chamberForecasts };
  } catch (error) {
    console.error("Failed to load layout data in layout load function:", error);
    let races = [];
    let chamberForecasts = {
      house: "House narrative overview loading...",
      senate: "Senate narrative overview loading...",
      governors: "Gubernatorial narrative overview loading...",
    };
    try {
      races = await getRaceSummaries(fetch);
    } catch (_) {}
    try {
      chamberForecasts = await getChamberForecasts(fetch);
    } catch (_) {}
    return { races, chamberForecasts };
  }
};
