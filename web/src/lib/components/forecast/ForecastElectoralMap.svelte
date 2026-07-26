<script lang="ts">
  import USMap from "$lib/components/USMap.svelte";
  import type { ForecastTab } from "$lib/utils/forecast";
  import type { StateTooltip } from "$lib/utils/forecastPresentation";

  export let activeTab: ForecastTab;
  export let activeStates: Set<string>;
  export let selectedState: string | null;
  export let stateRaceCounts: Record<string, number>;
  export let stateColors: Record<string, string>;
  export let stateTooltips: Record<string, StateTooltip>;
  export let onStateClick: (state: string) => void;
  export let onClearFilter: () => void;

  function handleStateClick(event: CustomEvent<string>) {
    onStateClick(event.detail);
  }
</script>

<!-- Map Canvas Card -->
<div
  class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md flex flex-col min-h-[380px] h-full"
>
  <div
    class="flex items-center justify-between border-b border-stroke/40 pb-4 mb-4"
  >
    <div>
      <h2 class="text-lg font-bold text-content">Electoral Map</h2>
      <p class="text-xs text-content-subtle">
        Shaded by projected rating or holdover representation
      </p>
    </div>
    {#if selectedState}
      <button
        on:click={onClearFilter}
        class="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-semibold flex items-center gap-1 bg-blue-50 dark:bg-blue-950/40 px-2.5 py-1 rounded-lg border border-blue-200/50 dark:border-blue-900/50"
      >
        Clear Map Filter: {selectedState} x
      </button>
    {/if}
  </div>

  <div
    class="relative w-full py-2 flex flex-1 items-center justify-center min-h-[320px]"
  >
    <USMap
      {activeStates}
      {selectedState}
      raceCounts={stateRaceCounts}
      {stateColors}
      {stateTooltips}
      on:stateClick={handleStateClick}
    />
  </div>

  <!-- Map Colors Legend -->
  <div class="border-t border-stroke/40 pt-4 mt-4 space-y-3">
    <span class="text-xs font-semibold text-content-muted block"
      >Map Legend</span
    >
    <div class="flex flex-wrap gap-x-4 gap-y-2 justify-center lg:justify-start">
      <div class="flex items-center gap-1.5 text-xs text-content-muted">
        <span
          class="w-3.5 h-3.5 rounded bg-blue-700 block border border-blue-950/10"
        ></span> Safe D
      </div>
      <div class="flex items-center gap-1.5 text-xs text-content-muted">
        <span
          class="w-3.5 h-3.5 rounded bg-blue-400 block border border-blue-950/10"
        ></span> Likely D
      </div>
      <div class="flex items-center gap-1.5 text-xs text-content-muted">
        <span
          class="w-3.5 h-3.5 rounded bg-blue-200 block border border-blue-950/10"
        ></span> Lean/Tilt D
      </div>
      <div class="flex items-center gap-1.5 text-xs text-content-muted">
        <span
          class="w-3.5 h-3.5 rounded bg-slate-200 dark:bg-slate-700 block border border-slate-900/10"
        ></span> Toss-up
      </div>
      <div class="flex items-center gap-1.5 text-xs text-content-muted">
        <span
          class="w-3.5 h-3.5 rounded bg-red-200 block border border-red-950/10"
        ></span> Lean/Tilt R
      </div>
      <div class="flex items-center gap-1.5 text-xs text-content-muted">
        <span
          class="w-3.5 h-3.5 rounded bg-red-400 block border border-red-950/10"
        ></span> Likely R
      </div>
      <div class="flex items-center gap-1.5 text-xs text-content-muted">
        <span
          class="w-3.5 h-3.5 rounded bg-red-700 block border border-red-950/10"
        ></span> Safe R
      </div>
      {#if activeTab !== "house"}
        <div class="flex items-center gap-1.5 text-xs text-content-muted">
          <span
            class="w-3.5 h-3.5 rounded block border border-blue-500/30 border-dashed"
            style="background-color: var(--color-holdover-d);"
          ></span> Dem Holdover
        </div>
        <div class="flex items-center gap-1.5 text-xs text-content-muted">
          <span
            class="w-3.5 h-3.5 rounded block border border-red-500/30 border-dashed"
            style="background-color: var(--color-holdover-r);"
          ></span> GOP Holdover
        </div>
      {/if}
    </div>
  </div>
</div>
