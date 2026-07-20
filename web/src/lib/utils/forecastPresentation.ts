import type { ForecastRating, RaceSummary } from "$lib/types";
import {
  formatRating,
  normalizeForecastParty,
  parseSeatDistributionKey,
} from "$lib/utils/forecast";

export function partyClass(party: string): string {
  if (party === "Democratic") return "text-blue-600 dark:text-blue-400";
  if (party === "Republican") return "text-red-600 dark:text-red-400";
  return "text-content-muted";
}

export function ratingClass(rating: ForecastRating): string {
  if (rating.endsWith("_d"))
    return "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-200 dark:border-blue-800/60";
  if (rating.endsWith("_r"))
    return "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-200 dark:border-red-800/60";
  return "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-800/40 dark:text-slate-200 dark:border-slate-700/60";
}

export function colorForRating(rating: ForecastRating): string {
  return `var(--color-${rating.replace("_", "-")})`;
}

export function ratingCompetitiveness(rating: ForecastRating): number {
  if (rating === "tossup") return 0;
  if (rating.startsWith("tilt_")) return 1;
  if (rating.startsWith("lean_")) return 2;
  if (rating.startsWith("likely_")) return 3;
  if (rating.startsWith("safe_")) return 4;
  return 5;
}

export function summarizeStateForecast(stateRaces: RaceSummary[]) {
  const forecasted = stateRaces.filter((race) => race.forecast);
  const sorted = [...forecasted].sort((a, b) => {
    const aForecast = a.forecast!;
    const bForecast = b.forecast!;
    const priority =
      ratingCompetitiveness(aForecast.rating) -
      ratingCompetitiveness(bForecast.rating);
    if (priority !== 0) return priority;
    return (
      Math.abs((aForecast.win_probability ?? 0.5) - 0.5) -
      Math.abs((bForecast.win_probability ?? 0.5) - 0.5)
    );
  });

  return {
    primary: sorted[0],
    forecastedCount: forecasted.length,
    competitiveCount: forecasted.filter(
      (race) => ratingCompetitiveness(race.forecast!.rating) <= 2,
    ).length,
    details: sorted.slice(0, 3).map((race) => {
      const forecast = race.forecast!;
      const party = normalizeForecastParty(
        forecast.predicted_winner_party,
        forecast.party_probabilities,
        race.candidates,
      );
      const winProb = forecast.win_probability
        ? `, ${Math.round(forecast.win_probability * 100)}% ${
            party === "Democratic" ? "D" : party === "Republican" ? "R" : party
          }`
        : "";
      return `${race.title ?? race.id}: ${formatRating(
        forecast.rating,
      )}${winProb}`;
    }),
  };
}

export function probability(value?: number | null): string {
  if (value === undefined || value === null) return "n/a";
  if (value >= 1) return ">99%";
  if (value <= 0) return "<1%";
  return `${Math.round(value * 100)}%`;
}

export function probabilityOneDecimal(value?: number | null): string {
  if (value === undefined || value === null) return "n/a";
  return `${(value * 100).toFixed(1)}%`;
}

export function marketSignalTarget(signal: {
  matched_to: string;
  matched_party?: string;
}): string {
  if (signal.matched_party && signal.matched_party !== signal.matched_to) {
    return `${signal.matched_to} (${signal.matched_party})`;
  }
  return signal.matched_to;
}

export function marketSpread(signal: {
  yes_bid?: number | null;
  yes_ask?: number | null;
}): string | null {
  if (
    typeof signal.yes_bid !== "number" ||
    typeof signal.yes_ask !== "number"
  ) {
    return null;
  }
  return `${probabilityOneDecimal(signal.yes_bid)} bid / ${probabilityOneDecimal(
    signal.yes_ask,
  )} ask`;
}

export function marketAsOf(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function oneDecimal(value?: number | null): string {
  if (value === undefined || value === null) return "n/a";
  return value.toFixed(1);
}

export interface SeatOutcomeChart {
  outcomes: {
    key: string;
    probability: number;
    dSeats: number;
    rSeats: number;
  }[];
  maxProbability: number;
  svgData: {
    fillPath: string;
    strokePath: string;
    points: {
      x: number;
      y: number;
      dSeats: number;
      rSeats: number;
      prob: number;
    }[];
    tieX: number;
    minD: number;
    maxD: number;
  };
}

export function buildSeatOutcomeChart(
  distribution: Record<string, number>,
  tieThreshold = 51,
): SeatOutcomeChart {
  const outcomes = Object.entries(distribution)
    .map(([key, probability]) => ({
      key,
      probability,
      ...parseSeatDistributionKey(key),
    }))
    .sort((a, b) => b.dSeats - a.dSeats);
  const maxProbability = Math.max(
    ...outcomes.map((outcome) => outcome.probability),
    0.01,
  );

  if (outcomes.length === 0) {
    return {
      outcomes,
      maxProbability,
      svgData: {
        fillPath: "",
        strokePath: "",
        points: [],
        tieX: 150,
        minD: 45,
        maxD: 55,
      },
    };
  }

  const minD = Math.min(...outcomes.map((outcome) => outcome.dSeats));
  const maxD = Math.max(...outcomes.map((outcome) => outcome.dSeats));
  const span = maxD - minD || 1;
  const points = outcomes.map((outcome) => ({
    x: 15 + ((outcome.dSeats - minD) / span) * 270,
    y: 85 - (outcome.probability / maxProbability) * 75,
    dSeats: outcome.dSeats,
    rSeats: outcome.rSeats,
    prob: outcome.probability,
  }));

  let fillPath = `M ${points[0].x} 85 `;
  let strokePath = `M ${points[0].x} ${points[0].y} `;
  for (const point of points) {
    fillPath += `L ${point.x} ${point.y} `;
    strokePath += `L ${point.x} ${point.y} `;
  }
  fillPath += `L ${points[points.length - 1].x} 85 Z`;

  const tieX =
    tieThreshold < minD
      ? 15
      : tieThreshold > maxD
        ? 285
        : 15 + ((tieThreshold - minD) / span) * 270;

  return {
    outcomes,
    maxProbability,
    svgData: { fillPath, strokePath, points, tieX, minD, maxD },
  };
}
