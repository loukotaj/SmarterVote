import type { PageLoad } from "./$types";
import {
  loadPrerenderChamberForecasts,
  loadPrerenderSummaries,
} from "$lib/prerenderData";
import type { ChamberForecasts, RaceSummary } from "$lib/types";
import { toForecastRaceSummaries } from "$lib/utils/publicRaceSummaries";

const EMPTY_CHAMBER_FORECASTS: ChamberForecasts = {
  house: "",
  senate: "",
  governors: "",
};

export const load: PageLoad = async ({ fetch }) => {
  const [racesResult, forecastsResult] = await Promise.allSettled([
    loadPrerenderSummaries(fetch),
    loadPrerenderChamberForecasts(fetch),
  ]);

  return {
    races:
      racesResult.status === "fulfilled"
        ? toForecastRaceSummaries(racesResult.value)
        : ([] as RaceSummary[]),
    chamberForecasts:
      forecastsResult.status === "fulfilled"
        ? forecastsResult.value
        : EMPTY_CHAMBER_FORECASTS,
  };
};
