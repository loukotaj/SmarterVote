<script lang="ts">
  import type { RaceSummary } from "$lib/types";
  import USMap from "$lib/components/USMap.svelte";
  import RaceCard from "$lib/components/RaceCard.svelte";
  import { page } from "$app/stores";
  import { goto } from "$app/navigation";
  import { browser } from "$app/environment";
  import { canonicalRaceState } from "$lib/utils/states";
  export let races: RaceSummary[] = [];
  import { debounce } from "$lib/utils/debounce";

  const PAGE_SIZE = 24;
  let loading = false;
  let visibleRaceCount = PAGE_SIZE;
  let previousFilterSignature = "";

  // Filter state
  let selectedState: string | null = null;
  let selectedOffice: string | null = null;
  let searchQuery = "";
  let debouncedSearchQuery = "";
  let mapExpanded = false;

  // Sync searchQuery with URL query parameter q reactively.
  // Use lastPageQ to avoid a reactive loop: typing updates searchQuery which
  // would re-trigger this block and reset the value before goto() completes.
  let lastPageQ = "";
  $: {
    if (browser) {
      const q = $page.url.searchParams.get("q") || "";
      if (q !== lastPageQ) {
        lastPageQ = q;
        searchQuery = q;
        debouncedSearchQuery = q;
      }
    }
  }

  const debouncedGoto = debounce((q: string) => {
    debouncedSearchQuery = q;
    const params = new URLSearchParams($page.url.searchParams);
    if (q) {
      params.set("q", q);
    } else {
      params.delete("q");
    }
    goto(`/elections/?${params.toString()}`, {
      replaceState: true,
      keepFocus: true,
      noScroll: true,
    });
  }, 150);

  function handleHeroSearchInput() {
    const q = searchQuery.trim();
    lastPageQ = q;
    debouncedGoto(q);
  }

  function clearHeroSearch() {
    searchQuery = "";
    debouncedSearchQuery = "";
    lastPageQ = "";
    const params = new URLSearchParams($page.url.searchParams);
    params.delete("q");
    goto(`/elections/?${params.toString()}`, {
      replaceState: true,
      keepFocus: true,
      noScroll: true,
    });
  }

  // States that have races — prefer explicit `state` field, fall back to `jurisdiction` for
  // older records where jurisdiction is already a plain state name.
  // Dynamically filtered by search query and office filters so the map highlights update.
  $: activeStates = new Set(
    races
      .filter((race) => {
        if (selectedOffice && officeShort(race.office) !== selectedOffice)
          return false;
        if (debouncedSearchQuery.trim()) {
          const q = debouncedSearchQuery.toLowerCase();
          return (
            race.title?.toLowerCase().includes(q) ||
            race.office?.toLowerCase().includes(q) ||
            race.jurisdiction?.toLowerCase().includes(q) ||
            canonicalRaceState(race)?.toLowerCase().includes(q) ||
            race.candidates.some(
              (c) =>
                c.name.toLowerCase().includes(q) ||
                c.party?.toLowerCase().includes(q),
            )
          );
        }
        return true;
      })
      .map(canonicalRaceState)
      .filter(Boolean) as string[],
  );

  // Compute matching candidates per state to show in map tooltips
  $: matchingCandidatesByState = (() => {
    const map: Record<string, string[]> = {};
    if (!debouncedSearchQuery.trim()) return map;
    const q = debouncedSearchQuery.toLowerCase();

    races.forEach((race) => {
      const stateKey = canonicalRaceState(race);
      if (!stateKey) return;

      const matchedNames: string[] = [];
      race.candidates.forEach((c) => {
        if (c.name.toLowerCase().includes(q)) {
          matchedNames.push(c.name);
        }
      });

      if (matchedNames.length > 0) {
        if (!map[stateKey]) map[stateKey] = [];
        matchedNames.forEach((name) => {
          if (!map[stateKey].includes(name)) {
            map[stateKey].push(name);
          }
        });
      }
    });
    return map;
  })();

  // Compute filtered race counts for active states to show in tooltips
  $: filteredRaceCounts = races
    .filter((race) => {
      if (selectedOffice && officeShort(race.office) !== selectedOffice)
        return false;
      if (debouncedSearchQuery.trim()) {
        const q = debouncedSearchQuery.toLowerCase();
        return (
          race.title?.toLowerCase().includes(q) ||
          race.office?.toLowerCase().includes(q) ||
          race.jurisdiction?.toLowerCase().includes(q) ||
          canonicalRaceState(race)?.toLowerCase().includes(q) ||
          race.candidates.some(
            (c) =>
              c.name.toLowerCase().includes(q) ||
              c.party?.toLowerCase().includes(q),
          )
        );
      }
      return true;
    })
    .reduce<Record<string, number>>((acc, r) => {
      const stateKey = canonicalRaceState(r);
      if (stateKey) acc[stateKey] = (acc[stateKey] ?? 0) + 1;
      return acc;
    }, {});

  // unique short office names for filter chips - raising the bar
  function officeShort(office: string | undefined): string {
    if (!office) return "Other";
    const o = office.toLowerCase();
    if (o.includes("senate")) return "Senate";
    if (o.includes("governor") || o.includes("gubernatorial"))
      return "Governor";
    if (o.includes("house") || o.includes("representative")) return "House";
    if (o.includes("secretary")) return "Sec. of State";
    if (o.includes("attorney")) return "Atty. General";
    return "Other";
  }

  $: officeTypes = (() => {
    const mapped = races.map((r) => officeShort(r.office));
    const types = [...new Set(mapped)].filter((x) => x !== "Other").sort();
    if (mapped.includes("Other")) {
      types.push("Other");
    }
    return types;
  })();

  // filtering chain: state > office > text
  $: filteredRaces = races
    .filter((race) => {
      const raceState = canonicalRaceState(race);
      if (selectedState && raceState !== selectedState) return false;
      if (selectedOffice && officeShort(race.office) !== selectedOffice)
        return false;
      if (debouncedSearchQuery.trim()) {
        const q = debouncedSearchQuery.toLowerCase();
        return (
          race.title?.toLowerCase().includes(q) ||
          race.office?.toLowerCase().includes(q) ||
          race.jurisdiction?.toLowerCase().includes(q) ||
          canonicalRaceState(race)?.toLowerCase().includes(q) ||
          race.candidates.some(
            (c) =>
              c.name.toLowerCase().includes(q) ||
              c.party?.toLowerCase().includes(q),
          )
        );
      }
      return true;
    })
    .sort((a, b) => {
      const stateOrder = (canonicalRaceState(a) ?? "").localeCompare(
        canonicalRaceState(b) ?? "",
      );
      return stateOrder || (a.title ?? "").localeCompare(b.title ?? "");
    });

  $: filterSignature = JSON.stringify([
    selectedState,
    selectedOffice,
    debouncedSearchQuery.trim(),
  ]);
  $: if (filterSignature !== previousFilterSignature) {
    previousFilterSignature = filterSignature;
    visibleRaceCount = PAGE_SIZE;
  }
  $: visibleRaces = filteredRaces.slice(0, visibleRaceCount);

  function handleStateClick(e: CustomEvent<string>) {
    const state = e.detail;
    selectedState = selectedState === state ? null : state;
    selectedOffice = null;
  }

  $: hasActiveFilters =
    selectedState || selectedOffice || debouncedSearchQuery.trim();

  function clearFilters() {
    selectedState = null;
    selectedOffice = null;
    searchQuery = "";
    debouncedSearchQuery = "";

    const params = new URLSearchParams($page.url.searchParams);
    params.delete("q");
    goto(`/elections/?${params.toString()}`, {
      replaceState: true,
      keepFocus: true,
      noScroll: true,
    });
  }
</script>

<div class="max-w-7xl mx-auto px-4 py-8 sm:py-10">
  <!-- Alpha strip -->
  <div
    class="flex items-center gap-2 bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg px-4 py-2 mb-6 text-xs text-amber-800 dark:text-amber-200"
  >
    <svg
      class="w-4 h-4 flex-shrink-0 text-amber-500"
      fill="currentColor"
      viewBox="0 0 20 20"
    >
      <path
        fill-rule="evenodd"
        d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
        clip-rule="evenodd"
      />
    </svg>
    <span
      ><strong>Early access:</strong> AI-generated research can be wrong or outdated.
      Check the linked sources and use your own judgment.</span
    >
  </div>

  <!-- Hero -->
  <header class="text-center mb-8 sm:mb-10 flex flex-col items-center">
    <h1
      class="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-content tracking-tight mb-3"
    >
      Explore elections.
    </h1>
    <p class="text-lg sm:text-xl text-content-muted max-w-xl mx-auto mb-6">
      Browse sourced candidate research for U.S. House, Senate, and governor
      races by state, office, or candidate.
    </p>

    <!-- Hero Search Bar -->
    <div
      class="relative w-full max-w-lg shadow-sm hover:shadow-md transition-shadow duration-300 rounded-full"
    >
      <label for="election-directory-search" class="sr-only">
        Search elections and candidates
      </label>
      <div
        class="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none"
      >
        <svg
          class="h-5 w-5 text-content-subtle"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2.5"
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
      </div>
      <input
        id="election-directory-search"
        type="text"
        bind:value={searchQuery}
        on:input={handleHeroSearchInput}
        placeholder="Search by candidate name, office, or state..."
        class="block w-full pl-11 pr-10 py-3 border border-stroke rounded-full text-base bg-surface placeholder-content-subtle focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-content transition-all duration-300"
      />
      {#if searchQuery.trim()}
        <button
          on:click={clearHeroSearch}
          class="absolute inset-y-0 right-0 pr-4 flex items-center text-content-subtle hover:text-content transition-colors"
          aria-label="Clear search query"
        >
          <svg
            class="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      {/if}
    </div>
  </header>

  <!-- Primary filters stay ahead of the optional map so results are reachable quickly. -->
  <div
    class="mb-6 flex flex-wrap items-center gap-2"
    aria-label="Filter elections by office"
  >
    {#if selectedState}
      <button
        type="button"
        on:click={() => {
          selectedState = null;
          selectedOffice = null;
        }}
        class="inline-flex min-h-11 items-center gap-1.5 rounded-full bg-blue-600 pl-3 pr-2 text-sm font-medium text-white shadow-sm"
        aria-label="Clear state filter: {selectedState}"
      >
        {selectedState}
        <svg
          class="h-3.5 w-3.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2.5"
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    {/if}

    {#each officeTypes as office}
      <button
        type="button"
        on:click={() => {
          selectedOffice = selectedOffice === office ? null : office;
        }}
        aria-pressed={selectedOffice === office}
        class="min-h-11 rounded-full border px-4 py-2 text-sm font-medium transition-colors
          {selectedOffice === office
          ? 'border-content bg-content text-surface'
          : 'border-stroke bg-surface text-content-muted hover:border-content-muted hover:text-content'}"
      >
        {office}
      </button>
    {/each}
  </div>

  <!-- Map section -->
  <section
    class="bg-surface border border-stroke rounded-2xl shadow-sm p-4 sm:p-6 mb-6"
  >
    <div class="flex items-center justify-between mb-3">
      <h2 class="text-base font-semibold text-content">
        {selectedState
          ? `${selectedState} · ${filteredRaceCounts[selectedState] ?? 0} race${
              (filteredRaceCounts[selectedState] ?? 0) !== 1 ? "s" : ""
            }`
          : "Select a state"}
      </h2>
      {#if selectedState}
        <button
          on:click={() => {
            selectedState = null;
            selectedOffice = null;
          }}
          class="text-xs text-content-subtle hover:text-content underline underline-offset-2 transition-colors"
        >
          Clear selection
        </button>
      {/if}
    </div>

    <!-- Mobile dropdown select, visible only on small viewports -->
    <div class="block sm:hidden mb-4">
      <label
        for="mobile-state-select"
        class="block text-xs font-semibold text-content-subtle mb-1"
      >
        Or select a state:
      </label>
      <select
        id="mobile-state-select"
        value={selectedState || ""}
        on:change={(e) => {
          const val = e.currentTarget.value;
          selectedState = val ? val : null;
          selectedOffice = null;
        }}
        class="block w-full px-3 py-2 border border-stroke rounded-lg text-sm bg-surface text-content focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all"
      >
        <option value="">All States</option>
        {#each [...activeStates].sort() as state}
          <option value={state}>
            {state} ({filteredRaceCounts[state] ?? 0} race{(filteredRaceCounts[
              state
            ] ?? 0) !== 1
              ? "s"
              : ""})
          </option>
        {/each}
      </select>
    </div>

    <button
      type="button"
      class="mb-3 inline-flex min-h-11 w-full items-center justify-between rounded-lg border border-stroke bg-surface-alt px-3 py-2 text-sm font-semibold text-content sm:hidden"
      aria-expanded={mapExpanded}
      aria-controls="election-state-map"
      on:click={() => (mapExpanded = !mapExpanded)}
    >
      {mapExpanded ? "Hide interactive map" : "Show interactive map"}
      <span aria-hidden="true">{mapExpanded ? "−" : "+"}</span>
    </button>
    <div id="election-state-map" class:hidden={!mapExpanded} class="sm:block">
      <USMap
        {activeStates}
        {selectedState}
        raceCounts={filteredRaceCounts}
        {matchingCandidatesByState}
        on:stateClick={handleStateClick}
      />
    </div>
  </section>

  <!-- Results grid -->
  <section>
    <div class="flex items-center justify-between mb-4">
      <p class="text-sm text-content-muted">
        {#if hasActiveFilters}
          <span class="font-medium text-content">{filteredRaces.length}</span>
          {filteredRaces.length === 1 ? "race" : "races"} found
          <button
            on:click={clearFilters}
            class="ml-2 underline underline-offset-2 hover:text-content transition-colors"
            >clear filters</button
          >
        {:else if !loading}
          Showing <span class="font-medium text-content"
            >{visibleRaces.length}</span
          >
          of <span class="font-medium text-content">{races.length}</span>
          races
        {/if}
      </p>
    </div>

    {#if loading}
      <!-- Loading spinner + skeleton grid -->
      <div class="flex justify-center items-center py-6">
        <svg
          class="animate-spin h-10 w-10 text-blue-500"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            class="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            stroke-width="4"
          />
          <path
            class="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        <span class="ml-3 text-content-muted text-sm">Loading races…</span>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {#each Array(6) as _}
          <div
            class="bg-surface border border-stroke rounded-xl h-40 animate-pulse"
          ></div>
        {/each}
      </div>
    {:else if filteredRaces.length === 0}
      <div class="text-center py-16 text-content-subtle">
        <svg
          class="mx-auto h-12 w-12 text-content-faint mb-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="1.5"
            d="M9.172 16.172a4 4 0 015.656 0M9 12h6m-6-4h6m2 5.291A7.962 7.962 0 0112 15c-2.34 0-4.47-.881-6.08-2.329C7.76 10.22 9.77 8 12.16 8c1.311 0 2.52.375 3.546 1.022M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <p class="text-lg font-medium text-content">No races found</p>
        <p class="mt-1 text-sm">
          {hasActiveFilters
            ? "Try adjusting your filters."
            : "No races have been published yet."}
        </p>
        {#if hasActiveFilters}
          <button
            on:click={clearFilters}
            class="mt-3 text-blue-600 hover:text-blue-700 text-sm underline underline-offset-2"
          >
            Clear all filters
          </button>
        {/if}
      </div>
    {:else}
      <div
        id="election-results-grid"
        class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
      >
        {#each visibleRaces as race (race.id)}
          <RaceCard {race} />
        {/each}
      </div>
      {#if visibleRaces.length < filteredRaces.length}
        <div class="mt-8 flex justify-center">
          <button
            type="button"
            class="min-h-11 rounded-lg border border-stroke bg-surface px-5 py-2.5 text-sm font-semibold text-content shadow-sm transition-colors hover:bg-surface-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
            aria-controls="election-results-grid"
            on:click={() => (visibleRaceCount += PAGE_SIZE)}
          >
            Show more races ({filteredRaces.length - visibleRaces.length}
            remaining)
          </button>
        </div>
      {/if}
    {/if}
  </section>
</div>
