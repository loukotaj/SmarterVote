<script lang="ts">
  import type { ChamberForecastDetails } from "$lib/types";
  import {
    filterForecastRaces,
    sortForecastRaces,
    type ForecastRace,
    type ForecastTab,
  } from "$lib/utils/forecast";
  import ForecastRaceFilters from "./ForecastRaceFilters.svelte";
  import ForecastRaceCard from "./ForecastRaceCard.svelte";

  export let races: ForecastRace[];
  export let activeTab: ForecastTab;
  export let selectedState: string | null;
  export let chamberSummary: ChamberForecastDetails | undefined;
  export let onClearStateFilter: () => void;

  let filterRating = "all";
  let filterParty = "all";
  let sortBy = "control_relevance";
  let visibleRaceCount = 9;
  let expandedRaceIds = new Set<string>();
  let expandedRaceTab: ForecastTab = activeTab;

  $: filteredRaces = filterForecastRaces(races, {
    selectedState,
    filterRating,
    filterParty,
  });
  $: sortedRaces = sortForecastRaces(filteredRaces, sortBy, chamberSummary);

  $: {
    // Reset visible race count on tab or filter change
    (activeTab, selectedState, filterRating, filterParty);
    visibleRaceCount = 9;
  }

  $: if (activeTab !== expandedRaceTab) {
    expandedRaceIds.clear();
    expandedRaceIds = expandedRaceIds;
    expandedRaceTab = activeTab;
  }

  function toggleExpand(raceId: string) {
    if (expandedRaceIds.has(raceId)) {
      expandedRaceIds.delete(raceId);
    } else {
      expandedRaceIds.add(raceId);
    }
    expandedRaceIds = expandedRaceIds;
  }

  function clearAllFilters() {
    onClearStateFilter();
    filterRating = "all";
    filterParty = "all";
  }
</script>

<!-- Active competitive/active races list -->
<section
  class="bg-surface border border-stroke rounded-2xl shadow-sm overflow-hidden"
>
  <ForecastRaceFilters
    {filterRating}
    {filterParty}
    {sortBy}
    {selectedState}
    resultCount={filteredRaces.length}
    onFilterRatingChange={(rating) => (filterRating = rating)}
    onFilterPartyChange={(party) => (filterParty = party)}
    onSortByChange={(value) => (sortBy = value)}
    onClearState={onClearStateFilter}
  />

  <!-- Empty state -->
  {#if filteredRaces.length === 0}
    <div class="p-12 text-center">
      <p class="text-base text-content-muted font-semibold">
        No forecasts found matching the selected filters.
      </p>
      {#if selectedState || filterRating !== "all" || filterParty !== "all"}
        <button
          type="button"
          on:click={clearAllFilters}
          class="mt-3 text-xs text-blue-600 hover:underline dark:text-blue-400 font-semibold"
        >
          Clear all filters
        </button>
      {/if}
    </div>
  {:else}
    <!-- Responsive Card Feed -->
    <div
      class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4 bg-surface-alt/10"
    >
      {#each sortedRaces.slice(0, visibleRaceCount) as race (race.id)}
        <ForecastRaceCard
          {race}
          isExpanded={expandedRaceIds.has(race.id)}
          onToggleExpand={() => toggleExpand(race.id)}
        />
      {/each}
    </div>
    {#if sortedRaces.length > visibleRaceCount}
      <div class="p-5 text-center border-t border-stroke/40 bg-surface-alt/5">
        <button
          on:click={() => (visibleRaceCount += 12)}
          class="px-5 py-2.5 bg-surface hover:bg-surface-alt border border-stroke/80 rounded-xl text-xs font-bold text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300 transition-all shadow-sm"
        >
          Show More Races ({sortedRaces.length - visibleRaceCount} remaining)
        </button>
      </div>
    {/if}
  {/if}
</section>
