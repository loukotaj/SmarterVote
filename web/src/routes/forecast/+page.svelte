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

  let filterRating: string = "all";
  let filterParty: string = "all";
  let sortBy: string = "competitiveness";
  let expandedRaceIds = new Set<string>();

  $: races = ($page.data.races as RaceSummary[] | undefined) ?? [];
  $: activeTab = browser
    ? parseForecastTab($page.url.searchParams.get("tab"))
    : "house";
  $: selectedState = browser
    ? $page.url.searchParams.get("state") || null
    : null;
  $: aggregate = aggregateForecasts(races, activeTab);

  $: chamberForecasts = $page.data.chamberForecasts;
  $: chamberNarrative = chamberForecasts?.[activeTab] || "";

  $: if (activeTab) {
    expandedRaceIds.clear();
    expandedRaceIds = expandedRaceIds;
  }

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

  function toggleExpand(raceId: string) {
    if (expandedRaceIds.has(raceId)) {
      expandedRaceIds.delete(raceId);
    } else {
      expandedRaceIds.add(raceId);
    }
    expandedRaceIds = expandedRaceIds;
  }

  function getRatingGroup(rating: ForecastRating): "safe" | "likely" | "lean" | "tossup" | "other" {
    const r = rating.toLowerCase();
    if (r.startsWith("safe")) return "safe";
    if (r.startsWith("likely")) return "likely";
    if (r.startsWith("lean") || r.startsWith("tilt")) return "lean";
    if (r.includes("tossup") || r.includes("toss-up")) return "tossup";
    return "other";
  }

  $: filteredRaces = aggregate.races
    .filter((race) => {
      // Apply map filter
      if (selectedState && getRaceState(race) !== selectedState) return false;

      // Apply rating filter
      if (filterRating !== "all") {
        const group = getRatingGroup(race.forecast.rating);
        if (group !== filterRating) return false;
      }

      // Apply party filter
      if (filterParty !== "all") {
        const party = normalizeForecastParty(race.forecast.predicted_winner_party);
        if (filterParty === "democrat" && party !== "Democratic") return false;
        if (filterParty === "republican" && party !== "Republican") return false;
      }

      return true;
    })
    .sort((a, b) => {
      if (sortBy === "state") {
        const stateA = getRaceState(a) || "";
        const stateB = getRaceState(b) || "";
        return stateA.localeCompare(stateB);
      }
      if (sortBy === "probability") {
        const probA = a.forecast.win_probability ?? 0;
        const probB = b.forecast.win_probability ?? 0;
        return probB - probA;
      }
      if (sortBy === "margin") {
        const marginA = Math.abs(a.forecast.margin_estimate ?? 0);
        const marginB = Math.abs(b.forecast.margin_estimate ?? 0);
        return marginB - marginA;
      }
      // default: competitiveness (probability closest to 50% first)
      const diffA = Math.abs((a.forecast.win_probability ?? 0.5) - 0.5);
      const diffB = Math.abs((b.forecast.win_probability ?? 0.5) - 0.5);
      return diffA - diffB;
    });

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
          2026 Election Forecast
        </h1>
        <p class="mt-2 text-base text-content-muted max-w-3xl">
          Nonpartisan model projections, interactive maps, and structured analysis for the 2026 House, Senate, and Governor races.
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
        Model status: Live
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

  <!-- Forecast at a glance narrative and quick metrics -->
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <!-- Chamber Narrative Block -->
    <div class="lg:col-span-2 bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md flex flex-col justify-between">
      <div>
        <h2 class="text-xs font-bold uppercase text-content-subtle tracking-wider mb-2">Chamber Outlook & Analysis</h2>
        <p class="text-base font-medium text-content leading-relaxed">
          {chamberNarrative || `Projections indicate a highly competitive cycle for the ${activeTab === 'governors' ? 'Governors' : activeTab === 'senate' ? 'Senate' : 'House'}.`}
        </p>
      </div>
      <div class="mt-4 flex items-center justify-between text-[10px] text-content-subtle border-t border-stroke/20 pt-3">
        <span>SmarterVote Nonpartisan Forecasting Model</span>
        {#if chamberForecasts?.updated_at}
          <span>Updated: {new Date(chamberForecasts.updated_at).toLocaleDateString()}</span>
        {/if}
      </div>
    </div>

    <!-- Quick Stats Grid -->
    <div class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md grid grid-cols-2 gap-4">
      <div class="flex flex-col justify-center border-b border-stroke/20 pb-2">
        <span class="text-[10px] font-bold uppercase text-content-subtle tracking-wider">Projected Control</span>
        <span class={`text-lg font-black mt-1 ${partyClass(controlParty)}`}>{controlParty}</span>
      </div>
      <div class="flex flex-col justify-center border-b border-stroke/20 pb-2">
        <span class="text-[10px] font-bold uppercase text-content-subtle tracking-wider">Toss-up Seats</span>
        <span class="text-lg font-black mt-1 text-content">{aggregate.ratingCounts.tossup || 0}</span>
      </div>
      <div class="flex flex-col justify-center pt-2">
        <span class="text-[10px] font-bold uppercase text-content-subtle tracking-wider">Projected Dem</span>
        <span class="text-lg font-black mt-1 text-blue-600 dark:text-blue-400">{aggregate.projected.Democratic ?? 0}</span>
      </div>
      <div class="flex flex-col justify-center pt-2">
        <span class="text-[10px] font-bold uppercase text-content-subtle tracking-wider">Projected GOP</span>
        <span class="text-lg font-black mt-1 text-red-600 dark:text-red-400">{aggregate.projected.Republican ?? 0}</span>
      </div>
    </div>
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
          <h2 class="text-lg font-bold text-content">Electoral Map</h2>
          <p class="text-xs text-content-subtle">
            Shaded by projected rating or holdover representation
          </p>
        </div>
        {#if selectedState}
          <button
            on:click={clearStateFilter}
            class="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-semibold flex items-center gap-1 bg-blue-50 dark:bg-blue-950/40 px-2.5 py-1 rounded-lg border border-blue-200/50 dark:border-blue-900/50"
          >
            Clear Map Filter: {selectedState} ×
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
        <span class="text-xs font-semibold text-content-muted block">Map Legend</span>
        <div
          class="flex flex-wrap gap-x-4 gap-y-2 justify-center lg:justify-start"
        >
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-blue-700 block border border-blue-950/10"
            /> Safe D
          </div>
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-blue-400 block border border-blue-950/10"
            /> Likely D
          </div>
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-blue-200 block border border-blue-950/10"
            /> Lean/Tilt D
          </div>
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-slate-200 dark:bg-slate-700 block border border-slate-900/10"
            /> Toss-up
          </div>
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-red-200 block border border-red-950/10"
            /> Lean/Tilt R
          </div>
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-red-400 block border border-red-950/10"
            /> Likely R
          </div>
          <div class="flex items-center gap-1.5 text-xs text-content-muted">
            <span
              class="w-3.5 h-3.5 rounded bg-red-700 block border border-red-950/10"
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
          {aggregate.label} Projected Seats
        </p>

        <h3
          class="mt-3 text-3xl font-extrabold text-content flex items-baseline gap-2"
        >
          <span class={partyClass(controlParty)}>{controlParty} Projected</span>
        </h3>

        <p class="mt-1 text-xs text-content-subtle font-medium">
          {aggregate.threshold} seats needed for majority
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
            <span>Total: {aggregate.totalExpected}</span>
            <span>Majority Line: {aggregate.threshold}</span>
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

  <!-- Seats Not Up in 2026 section -->
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
              ? "Governor Seats Not Up in 2026"
              : "Senate Seats Not Up in 2026"}
          </h2>
          <span
            class="bg-surface-alt text-content-muted font-bold text-xs px-2.5 py-0.5 rounded-full border border-stroke/60"
          >
            {aggregate.holdovers.length} {activeTab === "governors" ? "states" : "seats"}
          </span>
        </div>
        <span class="text-xs text-blue-600 dark:text-blue-400 font-semibold">
          {showHoldovers ? "Hide List ▲" : "Show List ▼"}
        </span>
      </button>

      {#if showHoldovers}
        <div class="p-5 bg-surface-alt/10">
          <p class="text-xs text-content-subtle mb-4">
            These seats are not up for election in 2026 and are factored into our control calculations based on current incumbent party representation.
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
    <!-- Filter and Sort Header bar -->
    <div class="px-5 py-4 border-b border-stroke/40 bg-surface-alt/10 flex flex-wrap items-center justify-between gap-4">
      <div class="flex flex-wrap items-center gap-3">
        <!-- Filter by Rating -->
        <div class="flex items-center gap-1.5">
          <label for="rating-filter" class="text-xs font-semibold text-content-subtle">Rating:</label>
          <select id="rating-filter" bind:value={filterRating} class="text-xs bg-surface border border-stroke/60 rounded-lg px-2 py-1 text-content font-medium focus:outline-none focus:ring-1 focus:ring-blue-500">
            <option value="all">All Ratings</option>
            <option value="tossup">Toss-ups</option>
            <option value="lean">Lean/Tilt</option>
            <option value="likely">Likely</option>
            <option value="safe">Safe</option>
          </select>
        </div>

        <!-- Filter by Party -->
        <div class="flex items-center gap-1.5">
          <label for="party-filter" class="text-xs font-semibold text-content-subtle">Favored:</label>
          <select id="party-filter" bind:value={filterParty} class="text-xs bg-surface border border-stroke/60 rounded-lg px-2 py-1 text-content font-medium focus:outline-none focus:ring-1 focus:ring-blue-500">
            <option value="all">All Parties</option>
            <option value="democrat">Democratic</option>
            <option value="republican">Republican</option>
          </select>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <!-- Sort By -->
        <div class="flex items-center gap-1.5">
          <label for="sort-by" class="text-xs font-semibold text-content-subtle">Sort by:</label>
          <select id="sort-by" bind:value={sortBy} class="text-xs bg-surface border border-stroke/60 rounded-lg px-2 py-1 text-content font-medium focus:outline-none focus:ring-1 focus:ring-blue-500">
            <option value="competitiveness">Competitiveness</option>
            <option value="probability">Win Probability</option>
            <option value="margin">Margin Estimate</option>
            <option value="state">State</option>
          </select>
        </div>

        {#if selectedState}
          <button
            on:click={clearStateFilter}
            class="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-bold bg-blue-50 dark:bg-blue-950/40 px-2 py-1 rounded-lg border border-blue-200/50"
          >
            State: {selectedState} ×
          </button>
        {/if}

        <span class="text-xs text-content-subtle font-semibold">
          {filteredRaces.length} races
        </span>
      </div>
    </div>

    <!-- Empty state -->
    {#if filteredRaces.length === 0}
      <div class="p-12 text-center">
        <p class="text-base text-content-muted font-semibold">
          No forecasts found matching the selected filters.
        </p>
        {#if selectedState || filterRating !== 'all' || filterParty !== 'all'}
          <button
            on:click={() => { clearStateFilter(); filterRating = 'all'; filterParty = 'all'; }}
            class="mt-3 text-xs text-blue-600 hover:underline dark:text-blue-400 font-semibold"
          >
            Clear all filters
          </button>
        {/if}
      </div>
    {:else}
      <!-- Responsive Card Feed -->
      <div class="divide-y divide-stroke/30">
        {#each filteredRaces as race (race.id)}
          {@const party = normalizeForecastParty(race.forecast.predicted_winner_party)}
          {@const rating = race.forecast.rating}
          {@const isExpanded = expandedRaceIds.has(race.id)}

          <div class="p-5 hover:bg-surface-alt/10 transition-colors flex flex-col gap-4">
            <!-- Card Header: Title, Rating, and Details Link -->
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div class="flex flex-col">
                <a
                  href={browser ? raceHref(race.id) : undefined}
                  class="text-base font-extrabold text-content hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                >
                  {race.title ?? race.id}
                </a>
                <span class="text-xs text-content-subtle mt-0.5 font-medium">
                  {race.jurisdiction ?? race.state ?? race.office}
                </span>
              </div>

              <div class="flex items-center gap-2 self-start sm:self-center">
                <span class={`inline-flex border rounded-full px-2.5 py-0.5 text-xs font-bold leading-none ${ratingClass(rating)}`}>
                  {formatRating(rating)}
                </span>
                <a
                  href={browser ? raceHref(race.id) : undefined}
                  class="text-xs text-content-subtle hover:text-blue-600 dark:hover:text-blue-400 font-bold bg-surface border border-stroke/60 px-2.5 py-1 rounded-lg transition-all"
                >
                  Details →
                </a>
              </div>
            </div>

            <!-- Card Metrics Dashboard -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
              <!-- Forecast Projections -->
              <div class="grid grid-cols-3 gap-2 bg-surface-alt/30 border border-stroke/40 rounded-xl p-3 text-center shadow-inner">
                <div class="flex flex-col justify-center border-r border-stroke/30 pr-1">
                  <span class="text-[9px] font-bold text-content-subtle uppercase tracking-wider">Projected</span>
                  <span class={`text-xs font-extrabold mt-0.5 truncate ${partyClass(party)}`}>
                    {race.forecast.predicted_winner_name || party}
                  </span>
                </div>
                <div class="flex flex-col justify-center border-r border-stroke/30">
                  <span class="text-[9px] font-bold text-content-subtle uppercase tracking-wider">Win Prob.</span>
                  <span class="text-xs font-black mt-0.5 text-content tabular-nums">
                    {probability(race.forecast.win_probability)}
                  </span>
                </div>
                <div class="flex flex-col justify-center pl-1">
                  <span class="text-[9px] font-bold text-content-subtle uppercase tracking-wider">Est. Margin</span>
                  <span class="text-xs font-extrabold mt-0.5 text-content tabular-nums">
                    {race.forecast.margin_estimate === undefined || race.forecast.margin_estimate === null
                      ? "n/a"
                      : `${race.forecast.margin_estimate.toFixed(1)}%`}
                  </span>
                </div>
              </div>

              <!-- Takeaway Text -->
              <div class="md:col-span-2 flex flex-col justify-center">
                <span class="text-[10px] font-bold text-content-subtle uppercase tracking-wider mb-0.5">Key Takeaway</span>
                <p class="text-xs text-content-muted leading-relaxed font-medium">
                  {race.forecast.takeaway || (race.forecast.rationale ? race.forecast.rationale.split(/[.!?]/)[0] + "." : "No summary narrative available.")}
                </p>
              </div>
            </div>

            <!-- Card Accordion Toggle -->
            <div class="flex items-center justify-between border-t border-stroke/10 pt-3">
              <button
                on:click={() => toggleExpand(race.id)}
                class="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-bold flex items-center gap-1 focus:outline-none"
              >
                <span class="inline-block transition-transform duration-200" style={isExpanded ? "transform: rotate(180deg);" : ""}>▼</span>
                {isExpanded ? "Hide Analysis" : "Expand Analysis"}
              </button>

              <span class="text-[10px] text-content-subtle font-medium">
                {race.forecast.based_on_poll_count} poll{race.forecast.based_on_poll_count === 1 ? "" : "s"} analyzed
              </span>
            </div>

            <!-- Expandable Drawer Content -->
            {#if isExpanded}
              <div class="mt-1 pt-4 border-t border-stroke/30 grid grid-cols-1 lg:grid-cols-2 gap-4 text-xs bg-surface-alt/10 rounded-xl p-4 shadow-inner">
                <!-- Left Column: Key Drivers & Uncertainty -->
                <div class="space-y-3">
                  <div>
                    <span class="font-bold text-content uppercase tracking-wider text-[10px] block mb-1">Key Drivers</span>
                    {#if race.forecast.key_reasons && race.forecast.key_reasons.length > 0}
                      <ul class="list-disc list-inside space-y-1 text-content-muted font-medium pl-1">
                        {#each race.forecast.key_reasons as reason}
                          <li>{reason}</li>
                        {/each}
                      </ul>
                    {:else}
                      <p class="text-content-subtle font-medium italic">No structured key drivers specified. Refer to the full assessment.</p>
                    {/if}
                  </div>

                  {#if race.forecast.uncertainty}
                    <div class="pt-2 border-t border-stroke/20">
                      <span class="font-bold text-content uppercase tracking-wider text-[10px] block mb-1">Risk Factors & Uncertainty</span>
                      <p class="text-content-muted font-medium leading-relaxed">{race.forecast.uncertainty}</p>
                    </div>
                  {/if}
                </div>

                <!-- Right Column: Full Rationale and Metadata -->
                <div class="space-y-3 flex flex-col justify-between">
                  <div>
                    <span class="font-bold text-content uppercase tracking-wider text-[10px] block mb-1">Full Assessment</span>
                    <p class="text-content-muted leading-relaxed font-medium whitespace-pre-wrap">{race.forecast.rationale}</p>
                  </div>

                  <div class="pt-2 border-t border-stroke/20 flex flex-wrap items-center justify-between gap-2 text-[10px] text-content-subtle font-medium">
                    {#if race.forecast.model}
                      <span>Model: {race.forecast.model}</span>
                    {/if}
                    {#if race.forecast.generated_at}
                      <span>Run date: {new Date(race.forecast.generated_at).toLocaleDateString()}</span>
                    {/if}
                  </div>
                </div>
              </div>
            {/if}
          </div>
        {/each}
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
            Races currently in the catalog pending forecast modeling
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
