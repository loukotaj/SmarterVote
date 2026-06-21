import type { PageLoad } from "./$types";
import { getChamberForecasts } from "$lib/api";

export const load: PageLoad = async ({ fetch }) => {
  return {
    chamberForecasts: await getChamberForecasts(fetch),
  };
};
