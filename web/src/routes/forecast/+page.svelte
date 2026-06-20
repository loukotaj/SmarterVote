<script lang="ts">
  import { browser } from "$app/environment";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import TabButton from "$lib/components/TabButton.svelte";
  import USMap from "$lib/components/USMap.svelte";
  import type { ForecastRating, RaceSummary } from "$lib/types";
  import {
    aggregateForecasts,
    formatNet,
    formatRating,
    normalizeForecastParty,
    getRaceState,
    isRaceInForecastTab,
    parseForecastTab,
    type ForecastTab,
    INCUMBENT_FALLBACKS,
  } from "$lib/utils/forecast";
  import { GOVERNOR_HOLDOVERS, SENATE_HOLDOVERS } from "$lib/utils/holdovers";

  const tabs: { id: ForecastTab; label: string }[] = [
    { id: "house", label: "House" },
    { id: "senate", label: "Senate" },
    { id: "governors", label: "Governors" },
  ];

  const ratingOrder: ForecastRating[] = [
    "safe_d",
    "likely_d",
    "lean_d",
    "tilt_d",
    "tossup",
    "tilt_r",
    "lean_r",
    "likely_r",
    "safe_r",
  ];

  let activeTab: ForecastTab = "house";
  let selectedState: string | null = null;
  let showHoldovers = false;

  $: races = ($page.data.races as RaceSummary[] | undefined) ?? [];
  $: activeTab = browser
    ? parseForecastTab($page.url.searchParams.get("tab"))
    : "house";
  $: selectedState = browser
    ? $page.url.searchParams.get("state") || null
    : null;
  $: aggregate = aggregateForecasts(races, activeTab);

  $: controlParty =
    (aggregate.projected.Democratic ?? 0) >= aggregate.threshold
      ? "Democratic"
      : (aggregate.projected.Republican ?? 0) >= aggregate.threshold
      ? "Republican"
      : "No clear control";

  // Filter active states for the map click handler
  $: activeStates = new Set(
    races
      .filter((r) => isRaceInForecastTab(r, activeTab))
      .map(getRaceState)
      .filter(Boolean) as string[]
  );

  // Dynamic colors and tooltips for the map
  let stateColors: Record<string, string> = {};
  let stateTooltips: Record<string, any> = {};

  $: {
    const colors: Record<string, string> = {};
    const tooltips: Record<string, any> = {};

    const activeRaces = races.filter((r) => isRaceInForecastTab(r, activeTab));

    if (activeTab === "governors") {
      // Process holdovers
      for (const [state, party] of Object.entries(GOVERNOR_HOLDOVERS)) {
        colors[state] =
          party === "Democratic"
            ? "var(--color-holdover-d)"
            : "var(--color-holdover-r)";
        tooltips[state] = {
          title: state,
          subtitle: "No election in 2026",
          badge: `${
            party === "Democratic" ? "Democratic" : "Republican"
          } Holdover`,
          badgeClass:
            party === "Democratic"
              ? "!bg-blue-600/90 !text-white"
              : "!bg-red-600/90 !text-white",
          details: ["Incumbent Governor holds seat"],
        };
      }

      // Process active races
      for (const r of activeRaces) {
        const state = getRaceState(r);
        if (!state) continue;

        if (r.forecast) {
          const rating = r.forecast.rating;
          colors[state] = `var(--color-${rating.replace("_", "-")})`;
          const winProbText = r.forecast.win_probability
            ? ` (${Math.round(r.forecast.win_probability * 100)}% prob.)`
            : "";
          const marginText =
            r.forecast.margin_estimate !== undefined &&
            r.forecast.margin_estimate !== null
              ? ` +${r.forecast.margin_estimate.toFixed(1)} pts`
              : "";

          tooltips[state] = {
            title: state,
            subtitle: "2026 Governor Race",
            badge: formatRating(rating),
            badgeClass: rating.endsWith("_d")
              ? "!bg-blue-600 !text-white"
              : rating.endsWith("_r")
              ? "!bg-red-600 !text-white"
              : "!bg-slate-500 !text-white",
            details: [
              `Projected: ${
                r.forecast.predicted_winner_name ||
                r.forecast.predicted_winner_party
              }${winProbText}`,
              `Est. Margin: ${marginText || "n/a"}`,
              r.forecast.rationale.length > 90
                ? r.forecast.rationale.slice(0, 90) + "..."
                : r.forecast.rationale,
            ],
          };
        } else {
          colors[state] = "var(--color-tossup)";
          tooltips[state] = {
            title: state,
            subtitle: "2026 Governor Race",
            badge: "Unforecasted",
            badgeClass: "!bg-slate-500 !text-white",
            details: ["No published model forecasts yet"],
          };
        }
      }
    } else if (activeTab === "senate") {
      // Process holdovers
      for (const [state, parties] of Object.entries(SENATE_HOLDOVERS)) {
        const isActive = activeStates.has(state);
        const holdoverSeats = isActive ? parties.slice(0, 1) : parties;

        if (!isActive) {
          if (holdoverSeats.length === 2) {
            const p1 = holdoverSeats[0];
            const p2 = holdoverSeats[1];
            if (p1 === p2) {
              colors[state] =
                p1 === "Democratic"
                  ? "var(--color-holdover-d)"
                  : "var(--color-holdover-r)";
            } else {
              colors[state] = "var(--color-tossup)";
            }
          } else {
            colors[state] =
              holdoverSeats[0] === "Democratic"
                ? "var(--color-holdover-d)"
                : "var(--color-holdover-r)";
          }

          const seatStrings = holdoverSeats.map((p) =>
            p === "Democratic" ? "Democrat" : "Republican"
          );
          tooltips[state] = {
            title: state,
            subtitle: "No election in 2026",
            badge: `${holdoverSeats.length} Holdover Seat${
              holdoverSeats.length > 1 ? "s" : ""
            }`,
            badgeClass: "!bg-slate-500 !text-white",
            details: seatStrings.map((s, idx) => `Seat ${idx + 1}: ${s}`),
          };
        }
      }

      // Process active races
      for (const r of activeRaces) {
        const state = getRaceState(r);
        if (!state) continue;

        const parties = SENATE_HOLDOVERS[state] || [];
        const holdoverSeat = parties.length > 0 ? parties[0] : null;

        if (r.forecast) {
          const rating = r.forecast.rating;
          colors[state] = `var(--color-${rating.replace("_", "-")})`;
          const winProbText = r.forecast.win_probability
            ? ` (${Math.round(r.forecast.win_probability * 100)}% prob.)`
            : "";
          const marginText =
            r.forecast.margin_estimate !== undefined &&
            r.forecast.margin_estimate !== null
              ? ` +${r.forecast.margin_estimate.toFixed(1)} pts`
              : "";

          const details = [
            `Projected: ${
              r.forecast.predicted_winner_name ||
              r.forecast.predicted_winner_party
            }${winProbText}`,
            `Est. Margin: ${marginText || "n/a"}`,
          ];
          if (holdoverSeat) {
            details.push(
              `Holdover Seat: ${
                holdoverSeat === "Democratic" ? "Democrat" : "Republican"
              }`
            );
          }
          details.push(
            r.forecast.rationale.length > 90
              ? r.forecast.rationale.slice(0, 90) + "..."
              : r.forecast.rationale
          );

          tooltips[state] = {
            title: state,
            subtitle: "2026 Senate Election",
            badge: formatRating(rating),
            badgeClass: rating.endsWith("_d")
              ? "!bg-blue-600 !text-white"
              : rating.endsWith("_r")
              ? "!bg-red-600 !text-white"
              : "!bg-slate-500 !text-white",
            details,
          };
        } else {
          colors[state] = "var(--color-tossup)";
          const details = ["No published model forecasts yet"];
          if (holdoverSeat) {
            details.push(
              `Holdover Seat: ${
                holdoverSeat === "Democratic" ? "Democrat" : "Republican"
              }`
            );
          }
          tooltips[state] = {
            title: state,
            subtitle: "2026 Senate Election",
            badge: "Unforecasted",
            badgeClass: "!bg-slate-500 !text-white",
            details,
          };
        }
      }
    } else {
      // House
      for (const r of activeRaces) {
        const state = getRaceState(r);
        if (!state) continue;

        colors[state] = "var(--map-active)";

        const stateRaces = activeRaces.filter((h) => getRaceState(h) === state);
        const count = stateRaces.length;
        const forecastedCount = stateRaces.filter((h) => h.forecast).length;

        tooltips[state] = {
          title: state,
          subtitle: `${count} competitive House seat${count > 1 ? "s" : ""}`,
          badge: `${forecastedCount}/${count} Forecasted`,
          badgeClass: "!bg-blue-600 !text-white",
          details: ["Click state to filter races below"],
        };
      }
    }

    stateColors = colors;
    stateTooltips = tooltips;
  }

  function handleStateClick(event: CustomEvent<string>) {
    const stateName = event.detail;
    setUrlState(activeTab, selectedState === stateName ? null : stateName);
  }

  function setActiveTab(tab: ForecastTab) {
    setUrlState(tab, null);
  }

  function setUrlState(tab: ForecastTab, state: string | null) {
    if (!browser) return;
    const params = new URLSearchParams($page.url.searchParams);
    if (tab === "house") {
      params.delete("tab");
    } else {
      params.set("tab", tab);
    }
    if (state) {
      params.set("state", state);
    } else {
      params.delete("state");
    }
    const query = params.toString();
    goto(`/forecast${query ? `?${query}` : ""}`, {
      replaceState: true,
      keepFocus: true,
      noScroll: true,
    });
  }

  $: filteredRaces = selectedState
    ? aggregate.races.filter((r) => getRaceState(r) === selectedState)
    : aggregate.races;

  $: filteredMissingRaces = selectedState
    ? aggregate.missingForecasts.filter(
        (r) => getRaceState(r) === selectedState
      )
    : aggregate.missingForecasts;

  function partyClass(party: string): string {
    if (party === "Democratic") return "text-blue-600 dark:text-blue-400";
    if (party === "Republican") return "text-red-600 dark:text-red-400";
    return "text-content-muted";
  }

  function ratingClass(rating: ForecastRating): string {
    if (rating.endsWith("_d"))
      return "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-200 dark:border-blue-800/60";
    if (rating.endsWith("_r"))
      return "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-200 dark:border-red-800/60";
    return "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-800/40 dark:text-slate-200 dark:border-slate-700/60";
  }

  function probability(value?: number): string {
    if (value === undefined || value === null) return "n/a";
    return `${Math.round(value * 100)}%`;
  }

  function clearStateFilter() {
    setUrlState(activeTab, null);
  }

  function raceHref(id: string): string {
    return `/races/${id}`;
  }

  const controlParties: ("Democratic" | "Republican" | "Other")[] = [
    "Democratic",
    "Republican",
    "Other",
  ];
</script>

<svelte:head>
  <title>Forecasts - Smarter.vote</title>
  <meta
    name="description"
    content="Informational AI forecasts and interactive maps for 2026 House, Senate, and Governor races."
  />
</svelte:head>

<div class="max-w-7xl mx-auto px-4 py-8 sm:py-10 space-y-8">
  <header>
    <div
      class="flex flex-col md:flex-row md:items-center md:justify-between gap-4"
    >
      <div>
        <h1
          class="text-4xl font-extrabold text-content tracking-tight bg-gradient-to-r from-blue-600 to-red-600 bg-clip-text text-transparent dark:from-blue-400 dark:to-red-400"
        >
          Election Forecast Dashboard
        </h1>
        <p class="mt-2 text-base text-content-muted max-w-3xl">
          Interactive AI forecasts and projections for the 2026 midterms. Shaded
          states represent forecast ratings or holdover representation. Click on
          any active state to drill down into competitive races.
        </p>
      </div>
      <div
        class="text-xs text-content-subtle border border-stroke/80 bg-surface-alt/40 backdrop-blur-md px-3 py-2 rounded-xl flex items-center gap-1.5 self-start md:self-auto"
      >
        <span class="relative flex h-2 w-2">
          <span
            class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"
          />
          <span
            class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"
          />
        </span>
        Model status: Published
      </div>
    </div>
  </header>

  <!-- Navigation Tab Bar -->
  <div class="border-b border-stroke/60 flex gap-1 overflow-x-auto">
    {#each tabs as tab}
      <TabButton
        active={activeTab === tab.id}
        onClick={() => setActiveTab(tab.id)}
      >
        {tab.label}
      </TabButton>
    {/each}
  </div>

  <!-- Interactive Map & Statistics Dashboard Grid -->
  <section
    class="grid grid-cols-1 lg:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.7fr)] gap-6 items-start"
  >
    <!-- Map Canvas Card -->
    <div
      class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md flex flex-col justify-between min-h-[480px]"
    >
      <div
        class="flex items-center justify-between border-b border-stroke/40 pb-4 mb-4"
      >
        <div>
          <h2 class="text-lg font-bold text-content">National Map</h2>
          <p class="text-xs text-content-subtle">
            Color-coded by AI forecast rating or seat holdover party
          </p>
        </div>
        {#if selectedState}
          <button
            on:click={clearStateFilter}
            class="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-semibold flex items-center gap-1 bg-blue-50 dark:bg-blue-950/40 px-2.5 py-1 rounded-lg border border-blue-200/50 dark:border-blue-900/50"
          >
            Clear map filter: {selectedState} ✕
          </button>
        {/if}
      </div>

      <div class="relative w-full py-4 flex items-center justify-center">
        <USMap
          {activeStates}
          {selectedState}
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
        <div
          class="flex flex-wrap gap-x-4 gap-y-2 justify-center lg:justify-start"
        >
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-blue-700 block border border-blue-900/10"
            /> Safe D
          </div>
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-blue-400 block border border-blue-900/10"
            /> Likely D
          </div>
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-blue-200 block border border-blue-900/10"
            /> Lean/Tilt D
          </div>
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-slate-200 dark:bg-slate-700 block border border-slate-900/10"
            /> Toss-up
          </div>
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-red-200 block border border-red-900/10"
            /> Lean/Tilt R
          </div>
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-red-400 block border border-red-900/10"
            /> Likely R
          </div>
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-red-700 block border border-red-900/10"
            /> Safe R
          </div>
          {#if activeTab !== "house"}
            <div class="flex items-center gap-1.5 text-xs text-content-muted">
              <span
                class="w-3.5 h-3.5 rounded bg-blue-500/20 dark:bg-blue-500/30 block border border-blue-500/30 border-dashed"
              /> Dem Holdover
            </div>
            <div class="flex items-center gap-1.5 text-xs text-content-muted">
              <span
                class="w-3.5 h-3.5 rounded bg-red-500/20 dark:bg-red-500/30 block border border-red-500/30 border-dashed"
              /> GOP Holdover
            </div>
          {/if}
        </div>
      </div>
    </div>

    <!-- Stats Panel Column -->
    <div class="space-y-6">
      <!-- Projection Summary Stat Card -->
      <div
        class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md"
      >
        <p
          class="text-xs font-bold uppercase text-content-subtle tracking-wider"
        >
          {aggregate.label} Control Projection
        </p>

        <h3
          class="mt-3 text-3xl font-extrabold text-content flex items-baseline gap-2"
        >
          <span class={partyClass(controlParty)}>{controlParty}</span>
        </h3>

        <p class="mt-1 text-xs text-content-subtle font-medium">
          {aggregate.threshold} seats needed for control
        </p>

        <!-- Seat Distribution Bar Chart -->
        <div class="mt-6 space-y-1.5">
          <div
            class="flex items-center justify-between text-xs font-bold text-content-muted"
          >
            <span>Democrat: {aggregate.projected.Democratic ?? 0}</span>
            <span>Republican: {aggregate.projected.Republican ?? 0}</span>
          </div>

          <div
            class="h-6 rounded-full overflow-hidden bg-surface-alt flex border border-stroke/60"
          >
            <div
              class="bg-blue-600 dark:bg-blue-500 transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner"
              style={`width: ${Math.min(
                100,
                ((aggregate.projected.Democratic ?? 0) /
                  aggregate.totalExpected) *
                  100
              )}%`}
              title="Democratic projected seats"
            >
              {#if (aggregate.projected.Democratic ?? 0) > 20}
                {aggregate.projected.Democratic}
              {/if}
            </div>
            {#if aggregate.projected.Other}
              <div
                class="bg-slate-400 dark:bg-slate-500 transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner"
                style={`width: ${Math.min(
                  100,
                  ((aggregate.projected.Other ?? 0) / aggregate.totalExpected) *
                    100
                )}%`}
                title="Other projected seats"
              >
                {aggregate.projected.Other}
              </div>
            {/if}
            <div
              class="bg-red-600 dark:bg-red-500 transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner ml-auto"
              style={`width: ${Math.min(
                100,
                ((aggregate.projected.Republican ?? 0) /
                  aggregate.totalExpected) *
                  100
              )}%`}
              title="Republican projected seats"
            >
              {#if (aggregate.projected.Republican ?? 0) > 20}
                {aggregate.projected.Republican}
              {/if}
            </div>
          </div>

          <div
            class="flex justify-between text-[10px] text-content-subtle px-1"
          >
            <span>Total Expected: {aggregate.totalExpected}</span>
            <span>Majority line: {aggregate.threshold}</span>
          </div>
        </div>

        <!-- Net Seats Change Grid -->
        <div class="mt-6 pt-5 border-t border-stroke/40 grid grid-cols-3 gap-3">
          {#each controlParties as party}
            <div
              class="bg-surface-alt/40 border border-stroke/40 rounded-xl px-2.5 py-2 text-center shadow-inner"
            >
              <div
                class="text-[10px] text-content-subtle font-bold uppercase tracking-wider"
              >
                {party.slice(0, 3)}
              </div>
              <div class={`text-xl font-black mt-1 ${partyClass(party)}`}>
                {aggregate.projected[party] ?? 0}
              </div>
              <div
                class="text-[10px] text-content-subtle font-semibold tabular-nums mt-0.5"
              >
                {formatNet(aggregate.netChange[party] ?? 0)} net
              </div>
            </div>
          {/each}
        </div>
      </div>

      <!-- Ratings Counts Grid Card -->
      <div
        class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md"
      >
        <p
          class="text-xs font-bold uppercase text-content-subtle tracking-wider mb-4"
        >
          Forecast Ratings Breakdown
        </p>
        <div class="grid grid-cols-3 gap-2">
          {#each ratingOrder as rating}
            <div
              class={`border rounded-xl px-2 py-1.5 text-center transition-all ${ratingClass(
                rating
              )}`}
            >
              <div class="text-[10px] font-bold leading-tight truncate">
                {formatRating(rating)}
              </div>
              <div class="text-lg font-black mt-1 tabular-nums">
                {aggregate.ratingCounts[rating] ?? 0}
              </div>
            </div>
          {/each}
        </div>
      </div>
    </div>
  </section>

  <!-- Holdover Breakdown Details section -->
  {#if activeTab !== "house"}
    <section
      class="bg-surface border border-stroke rounded-2xl shadow-sm overflow-hidden"
    >
      <!-- Toggle header -->
      <button
        on:click={() => (showHoldovers = !showHoldovers)}
        class="w-full px-5 py-4 border-b border-stroke/40 flex items-center justify-between text-left hover:bg-surface-alt/30 transition-colors"
      >
        <div class="flex items-center gap-3">
          <h2 class="text-base font-bold text-content">
            {activeTab === "governors"
              ? "Governor Holdover States"
              : "Senate Holdover Seats"}
          </h2>
          <span
            class="bg-surface-alt text-content-muted font-bold text-xs px-2.5 py-0.5 rounded-full border border-stroke/60"
          >
            {aggregate.holdovers.length}
            {activeTab === "governors" ? "states" : "seats"}
          </span>
        </div>
        <span class="text-xs text-blue-600 dark:text-blue-400 font-semibold">
          {showHoldovers ? "Hide Details ▲" : "Show Details ▼"}
        </span>
      </button>

      {#if showHoldovers}
        <div class="p-5 bg-surface-alt/10">
          <p class="text-xs text-content-subtle mb-4">
            These are states and seats that are not up for election in 2026.
            They are carried over into our majority projections using their
            current party control.
          </p>
          <div
            class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3"
          >
            {#each aggregate.holdovers as h}
              <div
                class="bg-surface border border-stroke/60 rounded-xl px-3 py-2 flex items-center justify-between shadow-sm"
              >
                <span class="text-xs font-bold text-content truncate pr-1"
                  >{h.state}</span
                >
                <span
                  class={`text-[10px] font-extrabold uppercase px-1.5 py-0.5 rounded-md border ${
                    h.party === "Democratic"
                      ? "bg-blue-500/10 text-blue-600 border-blue-500/20 dark:bg-blue-500/20 dark:text-blue-400"
                      : "bg-red-500/10 text-red-600 border-red-500/20 dark:bg-red-500/20 dark:text-red-400"
                  }`}
                >
                  {h.party === "Democratic" ? "D" : "R"}{h.count > 1
                    ? ` x${h.count}`
                    : ""}
                </span>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    </section>
  {/if}

  <!-- Active competitive/active races list -->
  <section
    class="bg-surface border border-stroke rounded-2xl shadow-sm overflow-hidden"
  >
    <div
      class="px-5 py-4 border-b border-stroke/40 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-surface-alt/10"
    >
      <div>
        <h2 class="text-base font-bold text-content">Competitive Forecasts</h2>
        <p class="text-xs text-content-subtle">
          AI evaluations and rationales for active 2026 midterm contests
        </p>
      </div>
      <div class="flex items-center gap-3">
        {#if selectedState}
          <span
            class="text-xs text-blue-600 dark:text-blue-400 font-bold bg-blue-100/50 dark:bg-blue-900/30 border border-blue-200/50 dark:border-blue-800/50 px-2.5 py-0.5 rounded-full"
          >
            Filtered: {selectedState}
          </span>
        {/if}
        <span class="text-xs text-content-muted font-bold">
          {filteredRaces.length} race{filteredRaces.length !== 1 ? "s" : ""} shown
        </span>
      </div>
    </div>

    {#if filteredRaces.length === 0}
      <div class="p-12 text-center">
        <p class="text-base text-content-muted font-semibold">
          No competitive {aggregate.label.toLowerCase()} forecasts matching the filter.
        </p>
        {#if selectedState}
          <button
            on:click={clearStateFilter}
            class="mt-3 text-xs text-blue-600 hover:underline dark:text-blue-400 font-semibold"
          >
            Clear state filter and show all
          </button>
        {/if}
      </div>
    {:else}
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead
            class="bg-surface-alt/40 border-b border-stroke/40 text-content-subtle text-left"
          >
            <tr>
              <th class="font-bold px-5 py-3">Race Info</th>
              <th class="font-bold px-5 py-3">AI Forecast Rating</th>
              <th class="font-bold px-5 py-3">Projected Winner</th>
              <th class="font-bold px-5 py-3 text-right">Win Prob.</th>
              <th class="font-bold px-5 py-3 text-right">Est. Margin</th>
              <th class="font-bold px-5 py-3">AI Assessment Rationale</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-stroke/40">
            {#each filteredRaces.slice(0, 100) as race}
              {@const party = normalizeForecastParty(
                race.forecast.predicted_winner_party
              )}
              <tr class="hover:bg-surface-alt/20 transition-colors">
                <td class="px-5 py-4 min-w-[260px]">
                  <a
                    href={browser ? raceHref(race.id) : undefined}
                    class="font-bold text-content hover:text-blue-600 dark:hover:text-blue-400 transition-colors block text-sm"
                  >
                    {race.title ?? race.id}
                  </a>
                  <div class="text-xs text-content-subtle mt-1 font-medium">
                    {race.jurisdiction ?? race.state ?? race.office}
                  </div>
                </td>
                <td class="px-5 py-4 whitespace-nowrap">
                  <span
                    class={`inline-flex border rounded-full px-2.5 py-0.5 text-xs font-bold leading-none ${ratingClass(
                      race.forecast.rating
                    )}`}
                  >
                    {formatRating(race.forecast.rating)}
                  </span>
                </td>
                <td class="px-5 py-4 whitespace-nowrap">
                  <div class="flex items-center gap-2">
                    <span class={`font-bold ${partyClass(party)}`}>
                      {race.forecast.predicted_winner_name ??
                        "Unknown Candidate"}
                    </span>
                  </div>
                  <span class="text-xs text-content-subtle font-medium">
                    {race.forecast.predicted_winner_party ??
                      "No party designated"}
                  </span>
                </td>
                <td
                  class="px-5 py-4 text-right font-black text-content tabular-nums whitespace-nowrap"
                >
                  {probability(race.forecast.win_probability)}
                </td>
                <td
                  class="px-5 py-4 text-right font-bold text-content tabular-nums whitespace-nowrap"
                >
                  {race.forecast.margin_estimate === undefined ||
                  race.forecast.margin_estimate === null
                    ? "n/a"
                    : `${race.forecast.margin_estimate.toFixed(1)} pts`}
                </td>
                <td class="px-5 py-4 min-w-[320px] max-w-md">
                  <div
                    class="text-xs text-content-muted leading-relaxed font-medium"
                  >
                    {race.forecast.rationale}
                  </div>
                  <div
                    class="text-[10px] text-content-subtle font-semibold mt-1.5 flex items-center gap-1.5"
                  >
                    <span
                      class="bg-surface-alt/80 border border-stroke/60 px-1.5 py-0.5 rounded leading-none"
                    >
                      {race.forecast.based_on_poll_count} poll{race.forecast
                        .based_on_poll_count === 1
                        ? ""
                        : "s"}
                    </span>
                    {#if race.forecast.model}
                      <span class="text-content-subtle font-medium"
                        >Evaluated by {race.forecast.model}</span
                      >
                    {/if}
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>

  <!-- Unforecasted Active Races section -->
  {#if filteredMissingRaces.length > 0}
    <section
      class="bg-surface border border-stroke rounded-2xl shadow-sm overflow-hidden opacity-85"
    >
      <div
        class="px-5 py-4 border-b border-stroke/40 flex items-center justify-between bg-surface-alt/10"
      >
        <div>
          <h2 class="text-base font-bold text-content-muted">
            Unforecasted Races ({filteredMissingRaces.length})
          </h2>
          <p class="text-xs text-content-subtle">
            Published races in cycle with pending forecast generations
          </p>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead
            class="bg-surface-alt/40 border-b border-stroke/40 text-content-subtle text-left"
          >
            <tr>
              <th class="font-bold px-5 py-3">Race Info</th>
              <th class="font-bold px-5 py-3">Status</th>
              <th class="font-bold px-5 py-3">Incumbent Party</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-stroke/40">
            {#each filteredMissingRaces as race}
              {@const stateName = getRaceState(race)}
              {@const fallback = stateName
                ? INCUMBENT_FALLBACKS[activeTab]?.[stateName]
                : undefined}
              <tr class="hover:bg-surface-alt/10 transition-colors">
                <td class="px-5 py-3">
                  <a
                    href={browser ? raceHref(race.id) : undefined}
                    class="font-semibold text-content hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    {race.title ?? race.id}
                  </a>
                </td>
                <td class="px-5 py-3 whitespace-nowrap">
                  <span
                    class="inline-flex border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-content-subtle rounded-full px-2 py-0.5 text-xs font-semibold leading-none"
                  >
                    Pending Model Run
                  </span>
                </td>
                <td class="px-5 py-3">
                  {#if fallback}
                    <span class={`font-semibold ${partyClass(fallback)}`}>
                      {fallback} (Incumbent Fallback)
                    </span>
                  {:else}
                    <span class="text-content-subtle">Unknown</span>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>
  {/if}
</div>
