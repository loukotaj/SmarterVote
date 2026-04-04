<script lang="ts">
  import { onMount } from "svelte";
  import type { RaceSummary } from "$lib/types";
  import { getRaceSummaries } from "$lib/api";
  import USMap from "$lib/components/USMap.svelte";
  import RaceCard from "$lib/components/RaceCard.svelte";

  let races: RaceSummary[] = [];
  let loading = true;

  onMount(async () => {
    races = await getRaceSummaries();
    loading = false;
  });

  // Filter state
  let selectedState: string | null = null;
  let selectedOffice: string | null = null;
  let searchQuery = "";

  // States that have races — prefer explicit `state` field, fall back to `jurisdiction` for
  // older records where jurisdiction is already a plain state name.
  $: activeStates = new Set(races.map((r) => r.state ?? r.jurisdiction).filter(Boolean) as string[]);

  // race counts per state for tooltip
  $: raceCounts = races.reduce<Record<string, number>>((acc, r) => {
    const stateKey = r.state ?? r.jurisdiction;
    if (stateKey) acc[stateKey] = (acc[stateKey] ?? 0) + 1;
    return acc;
  }, {});

  // unique short office names for filter chips
  function officeShort(office: string | undefined): string {
    if (!office) return "Other";
    const o = office.toLowerCase();
    if (o.includes("senate")) return "Senate";
    if (o.includes("governor") || o.includes("gubernatorial")) return "Governor";
    if (o.includes("house") || o.includes("representative")) return "House";
    if (o.includes("secretary")) return "Sec. of State";
    if (o.includes("attorney")) return "Atty. General";
    return office.length > 18 ? office.slice(0, 18) + "\u2026" : office;
  }

  $: officeTypes = [...new Set(races.map((r) => officeShort(r.office)))].sort();

  // stats
  $: totalCandidates = races.reduce((sum, r) => sum + r.candidates.length, 0);

  // filtering chain: state > office > text
  $: filteredRaces = races.filter((race) => {
    const raceState = race.state ?? race.jurisdiction;
    if (selectedState && raceState !== selectedState) return false;
    if (selectedOffice && officeShort(race.office) !== selectedOffice) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        race.title?.toLowerCase().includes(q) ||
        race.office?.toLowerCase().includes(q) ||
        race.jurisdiction?.toLowerCase().includes(q) ||
        race.candidates.some(
          (c) => c.name.toLowerCase().includes(q) || c.party?.toLowerCase().includes(q)
        )
      );
    }
    return true;
  });

  function handleStateClick(e: CustomEvent<string>) {
    const state = e.detail;
    selectedState = selectedState === state ? null : state;
    selectedOffice = null;
  }

  $: hasActiveFilters = selectedState || selectedOffice || searchQuery.trim();

  function clearFilters() {
    selectedState = null;
    selectedOffice = null;
    searchQuery = "";
  }
</script>

<svelte:head>
  <title>Smarter.vote — Know Your Candidates</title>
  <meta
    name="description"
    content="Clear, unbiased AI analysis of where candidates stand on the issues that matter. Browse races by state."
  />
</svelte:head>

<div class="max-w-7xl mx-auto px-4 py-8 sm:py-10">

  <!-- Alpha strip -->
  <div class="flex items-center gap-2 bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg px-4 py-2 mb-6 text-xs text-amber-800 dark:text-amber-200">
    <svg class="w-4 h-4 flex-shrink-0 text-amber-500" fill="currentColor" viewBox="0 0 20 20">
      <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
    </svg>
    <span><strong>Alpha:</strong> AI-generated content can be wrong or outdated. Always follow the source links and apply your own judgment.</span>
  </div>

  <!-- Hero -->
  <header class="text-center mb-8 sm:mb-10">
    <h1 class="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-content tracking-tight mb-3">
      Know your candidates.
    </h1>
    <p class="text-lg sm:text-xl text-content-muted max-w-xl mx-auto mb-5">
      Clear, unbiased analysis of where they stand.
    </p>
  </header>

  <!-- Map section -->
  <section class="bg-surface border border-stroke rounded-2xl shadow-sm p-4 sm:p-6 mb-6">
    <div class="flex items-center justify-between mb-3">
      <h2 class="text-base font-semibold text-content">
        {selectedState ? `${selectedState} · ${raceCounts[selectedState] ?? 0} race${(raceCounts[selectedState] ?? 0) !== 1 ? 's' : ''}` : 'Select a state'}
      </h2>
      {#if selectedState}
        <button
          on:click={() => { selectedState = null; selectedOffice = null; }}
          class="text-xs text-content-subtle hover:text-content underline underline-offset-2 transition-colors"
        >
          Clear selection
        </button>
      {:else}
        <p class="text-xs text-content-subtle">Click a highlighted state to filter races</p>
      {/if}
    </div>

    {#if loading}
      <div class="h-64 bg-surface-alt rounded-xl flex items-center justify-center">
        <svg class="animate-spin h-8 w-8 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
    {:else}
      <USMap
        {activeStates}
        {selectedState}
        {raceCounts}
        on:stateClick={handleStateClick}
      />
    {/if}
  </section>

  <!-- Filter bar -->
  <div class="flex flex-wrap items-center gap-2 mb-6">
    <!-- State chip (active) -->
    {#if selectedState}
      <button
        on:click={() => { selectedState = null; selectedOffice = null; }}
        class="inline-flex items-center gap-1.5 pl-3 pr-2 py-1.5 rounded-full text-sm font-medium bg-blue-600 text-white shadow-sm"
      >
        {selectedState}
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    {/if}

    <!-- Office type chips -->
    {#each officeTypes as office}
      <button
        on:click={() => { selectedOffice = selectedOffice === office ? null : office; }}
        class="px-3 py-1.5 rounded-full text-sm font-medium border transition-colors
          {selectedOffice === office
            ? 'bg-content text-surface border-content'
            : 'bg-surface border-stroke text-content-muted hover:border-content-muted hover:text-content'}"
      >
        {office}
      </button>
    {/each}

    <!-- Spacer -->
    <div class="flex-1 min-w-[8rem]" />

    <!-- Search -->
    <div class="relative">
      <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
        <svg class="h-4 w-4 text-content-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </div>
      <input
        type="text"
        bind:value={searchQuery}
        placeholder="Search candidates, races..."
        class="block w-full sm:w-64 pl-9 pr-3 py-1.5 border border-stroke rounded-full text-sm bg-surface placeholder-content-subtle focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-content"
      />
    </div>
  </div>

  <!-- Results grid -->
  <section>
    <div class="flex items-center justify-between mb-4">
      <p class="text-sm text-content-muted">
        {#if hasActiveFilters}
          <span class="font-medium text-content">{filteredRaces.length}</span> {filteredRaces.length === 1 ? 'race' : 'races'} found
          <button on:click={clearFilters} class="ml-2 underline underline-offset-2 hover:text-content transition-colors">clear filters</button>
        {:else if !loading}
          Showing all <span class="font-medium text-content">{races.length}</span> races
        {/if}
      </p>
    </div>

    {#if loading}
      <!-- Loading spinner + skeleton grid -->
      <div class="flex justify-center items-center py-6">
        <svg class="animate-spin h-10 w-10 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span class="ml-3 text-content-muted text-sm">Loading races…</span>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {#each Array(6) as _}
          <div class="bg-surface border border-stroke rounded-xl h-40 animate-pulse" />
        {/each}
      </div>
    {:else if filteredRaces.length === 0}
      <div class="text-center py-16 text-content-subtle">
        <svg class="mx-auto h-12 w-12 text-content-faint mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.172 16.172a4 4 0 015.656 0M9 12h6m-6-4h6m2 5.291A7.962 7.962 0 0112 15c-2.34 0-4.47-.881-6.08-2.329C7.76 10.22 9.77 8 12.16 8c1.311 0 2.52.375 3.546 1.022M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p class="text-lg font-medium text-content">No races found</p>
        <p class="mt-1 text-sm">
          {hasActiveFilters ? 'Try adjusting your filters.' : 'No races have been published yet.'}
        </p>
        {#if hasActiveFilters}
          <button on:click={clearFilters} class="mt-3 text-blue-600 hover:text-blue-700 text-sm underline underline-offset-2">
            Clear all filters
          </button>
        {/if}
      </div>
    {:else}
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {#each filteredRaces as race (race.id)}
          <RaceCard {race} />
        {/each}
      </div>
    {/if}
  </section>
</div>
