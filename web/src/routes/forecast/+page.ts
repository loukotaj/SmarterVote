import type { PageLoad } from "./$types";
import { getChamberForecasts } from "$lib/api";
import type { ChamberForecasts } from "$lib/types";

const EMPTY_CHAMBER_FORECASTS: ChamberForecasts = {
  house: "",
  senate: "",
  governors: "",
};

export const load: PageLoad = async ({ fetch }) => {
  try {
    return {
      chamberForecasts: await getChamberForecasts(fetch),
    };
  } catch {
    return { chamberForecasts: EMPTY_CHAMBER_FORECASTS };
  }
};
