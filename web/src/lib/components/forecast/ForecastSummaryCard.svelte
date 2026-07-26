<script lang="ts">
  import type { ForecastTab } from "$lib/utils/forecast";
  import ForecastSummaryStats from "./ForecastSummaryStats.svelte";
  import ForecastControlBar from "./ForecastControlBar.svelte";
  import ForecastSeatsBar from "./ForecastSeatsBar.svelte";
  import ForecastOverviewFooter from "./ForecastOverviewFooter.svelte";

  export let activeTab: ForecastTab;
  export let controlParty: "Democratic" | "Republican" | "Other";
  export let controlProbability: number | undefined;
  export let vpTiebreakParty: string | undefined;
  export let mostLikelyOutcome: { key: string; probability: number };
  export let tossupCount: number;
  export let competitiveRaceCount: number;
  export let outcomeProbabilities: Record<string, number> | undefined;
  export let projectedSeats: Record<string, number>;
  export let totalSeats: number;
  export let threshold: number;
  export let narrative: string;
  export let updatedAt: string | undefined;
</script>

<!-- Forecast Above-The-Fold Layout: Election Summary -->
<div
  class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md animate-fade-in"
>
  <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
    <!-- Left Column: Summary -->
    <ForecastSummaryStats
      {activeTab}
      {controlParty}
      {controlProbability}
      {vpTiebreakParty}
      {mostLikelyOutcome}
      {tossupCount}
      {competitiveRaceCount}
    />

    <!-- Right Column: Charts / Stats -->
    <div
      class="lg:col-span-6 flex flex-col space-y-6 bg-surface-alt/25 border border-stroke/60 rounded-2xl p-6"
    >
      <ForecastControlBar {activeTab} {outcomeProbabilities} {projectedSeats} />
      <ForecastSeatsBar {activeTab} {projectedSeats} {totalSeats} {threshold} />
    </div>

    <!-- Full-Width Bottom Row: Forecast Overview -->
    <ForecastOverviewFooter {narrative} {updatedAt} />
  </div>
</div>
