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

  let mobileMapOpen = false;
  $: mapPanelId = `forecast-map-${activeTab}`;

  $: stateOptions = [...activeStates].sort((a, b) => a.localeCompare(b));

  function handleStateClick(event: CustomEvent<string>) {
    onStateClick(event.detail);
  }

  function handleStateSelect(event: Event) {
    const state = (event.currentTarget as HTMLSelectElement).value;
    if (state) {
      onStateClick(state);
    } else {
      onClearFilter();
    }
  }
</script>

<!-- Map Canvas Card -->
<div
  class="flex h-full flex-col rounded-2xl border border-stroke bg-surface/60 p-4 shadow-sm backdrop-blur-md sm:p-6 lg:min-h-[380px]"
>
  <div
    class="flex flex-col items-start justify-between gap-2 border-b border-stroke/40 pb-4 mb-4 sm:flex-row sm:items-center"
  >
    <div>
      <h2 class="text-lg font-bold text-content">Electoral Map</h2>
      <p class="text-xs text-content-subtle">
        Shaded by projected rating or holdover representation
      </p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      {#if selectedState}
        <button
          on:click={onClearFilter}
          class="flex min-h-11 items-center gap-1 rounded-lg border border-blue-200/50 bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-600 hover:text-blue-500 dark:border-blue-900/50 dark:bg-blue-950/40 dark:text-blue-400 dark:hover:text-blue-300"
        >
          Clear Map Filter: {selectedState} x
        </button>
      {/if}
      <button
        type="button"
        on:click={() => (mobileMapOpen = !mobileMapOpen)}
        aria-expanded={mobileMapOpen}
        aria-controls={mapPanelId}
        class="inline-flex min-h-11 items-center rounded-lg border border-stroke bg-surface px-3 py-2 text-xs font-bold text-blue-600 lg:hidden dark:text-blue-400"
      >
        {mobileMapOpen ? "Hide interactive map" : "Show interactive map"}
      </button>
    </div>
  </div>

  <div
    id={mapPanelId}
    class="{mobileMapOpen ? 'flex' : 'hidden'} flex-1 flex-col lg:flex"
  >
    {#if stateOptions.length > 0}
      <div class="mb-3 lg:hidden">
        <label
          for="forecast-state-select"
          class="mb-1.5 block text-xs font-semibold text-content-muted"
        >
          Select a state
        </label>
        <select
          id="forecast-state-select"
          value={selectedState ?? ""}
          on:change={handleStateSelect}
          class="w-full rounded-lg border border-stroke bg-surface px-3 py-2 text-sm text-content focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="">All active states</option>
          {#each stateOptions as state}
            <option value={state}
              >{state} ({stateRaceCounts[state] ?? 0})</option
            >
          {/each}
        </select>
      </div>
    {/if}

    <div
      class="relative flex min-h-[260px] w-full flex-1 items-center justify-center py-2 lg:min-h-[320px]"
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
    <div class="mt-4 space-y-3 border-t border-stroke/40 pt-4">
      <span class="text-xs font-semibold text-content-muted block"
        >Map Legend</span
      >
      <div
        class="flex flex-wrap gap-x-4 gap-y-2 justify-center lg:justify-start"
      >
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
</div>
