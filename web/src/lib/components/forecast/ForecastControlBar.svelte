<script lang="ts">
  import type { ForecastTab } from "$lib/utils/forecast";
  import { probability } from "$lib/utils/forecastPresentation";

  export let activeTab: ForecastTab;
  export let outcomeProbabilities: Record<string, number> | undefined;
  export let projectedSeats: Record<string, number>;
</script>

<div class="space-y-3">
  <div class="flex items-center justify-between">
    <span
      class="text-xs font-bold uppercase text-content-subtle tracking-wider font-semibold"
      >{activeTab === "governors"
        ? "Control Probabilities"
        : "Chamber Control Probabilities"}</span
    >
    {#if activeTab === "senate" && outcomeProbabilities?.tie_50_50}
      <span
        class="text-[10px] font-semibold text-content-subtle bg-surface-alt px-2 py-0.5 rounded-md border border-stroke/60"
      >
        50-50 Tie: {probability(outcomeProbabilities.tie_50_50)}
      </span>
    {/if}
  </div>

  {#if outcomeProbabilities}
    {@const demProb = outcomeProbabilities.Democratic ?? 0}
    {@const gopProb = outcomeProbabilities.Republican ?? 0}
    {@const tieProb = outcomeProbabilities.tie_50_50 ?? 0}
    {@const otherProb = outcomeProbabilities.Other ?? 0}
    <div class="space-y-3">
      <div
        class="h-8 rounded-xl overflow-hidden bg-surface-alt flex border border-stroke/60 relative shadow-inner"
      >
        {#if demProb > 0}
          <div
            class="bg-blue-600 dark:bg-blue-500 transition-all duration-500 flex items-center justify-center font-black text-white text-xs"
            style="width: {demProb * 100}%"
            title="Democratic control probability: {probability(demProb)}"
          >
            {#if demProb > 0.15}
              Democratic {probability(demProb)}
            {/if}
          </div>
        {/if}
        {#if activeTab === "governors" && tieProb > 0}
          <div
            class="bg-slate-400 dark:bg-slate-500 transition-all duration-500 flex items-center justify-center font-black text-white text-xs"
            style="width: {tieProb * 100}%"
            title="Split / Tie probability: {probability(tieProb)}"
          >
            {#if tieProb > 0.15}
              Tie {probability(tieProb)}
            {/if}
          </div>
        {/if}
        {#if otherProb > 0}
          <div
            class="bg-slate-400 dark:bg-slate-500 transition-all duration-500 flex items-center justify-center font-black text-white text-xs"
            style="width: {otherProb * 100}%"
            title="Other control probability: {probability(otherProb)}"
          >
            {#if otherProb > 0.15}
              Other {probability(otherProb)}
            {/if}
          </div>
        {/if}
        {#if gopProb > 0}
          <div
            class="bg-red-600 dark:bg-red-500 transition-all duration-500 flex items-center justify-center font-black text-white text-xs ml-auto"
            style="width: {gopProb * 100}%"
            title="Republican control probability: {probability(gopProb)}"
          >
            {#if gopProb > 0.15}
              Republican {probability(gopProb)}
            {/if}
          </div>
        {/if}
      </div>

      <!-- Callout Note -->
      {#if activeTab === "senate" && outcomeProbabilities.tie_50_50 && !(projectedSeats.Democratic === 50 && projectedSeats.Republican === 50)}
        <div
          class="bg-surface-alt/40 border border-stroke/60 rounded-xl p-3 flex items-start gap-2.5"
        >
          <svg
            class="w-5 h-5 text-content-subtle shrink-0 mt-0.5"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            viewBox="0 0 24 24"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <p class="text-xs text-content-muted leading-relaxed font-medium">
            A {probability(outcomeProbabilities.tie_50_50)} 50-50 tie probability
            is counted as Republican control via VP tie-break, contributing to the
            Republican control advantage shown above.
          </p>
        </div>
      {/if}
    </div>
  {/if}
</div>
