<script lang="ts">
  import { browser } from "$app/environment";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import TabButton from "$lib/components/TabButton.svelte";
  import USMap from "$lib/components/USMap.svelte";
  import type { ChamberForecasts, ForecastRating, RaceSummary } from "$lib/types";
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
  let sortBy: string = "control_relevance";
  let expandedRaceIds = new Set<string>();
  let expandedRaceTab: ForecastTab = activeTab;

  $: races = ($page.data.races as RaceSummary[] | undefined) ?? [];
  $: activeTab = browser
    ? parseForecastTab($page.url.searchParams.get("tab"))
    : "house";
  $: selectedState = browser
    ? $page.url.searchParams.get("state") || null
    : null;
  $: aggregate = aggregateForecasts(races, activeTab);

  $: chamberForecasts = $page.data.chamberForecasts as ChamberForecasts | undefined;
  $: chamberSummary = chamberForecasts?.chambers?.[activeTab];
  $: chamberNarrative =
    chamberSummary?.narrative || chamberForecasts?.[activeTab] || "";

  $: if (activeTab !== expandedRaceTab) {
    expandedRaceIds.clear();
    expandedRaceIds = expandedRaceIds;
    expandedRaceTab = activeTab;
  }

  $: projectedSeats = chamberSummary?.projected_seats ?? aggregate.projected;
  $: expectedSeats = chamberSummary?.expected_seats;
  $: outcomeProbabilities = chamberSummary?.outcome_probabilities;
  $: totalSeats = chamberSummary?.total_seats ?? aggregate.totalExpected;
  $: threshold = chamberSummary?.threshold ?? aggregate.threshold;
  $: controlParty =
    chamberSummary?.control_party ??
    (activeTab === "senate" &&
    (aggregate.projected.Democratic ?? 0) === 50 &&
    (aggregate.projected.Republican ?? 0) === 50
      ? "Republican"
      : (aggregate.projected.Democratic ?? 0) >= aggregate.threshold
      ? "Democratic"
      : (aggregate.projected.Republican ?? 0) >= aggregate.threshold
      ? "Republican"
      : "Other");

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

  function getControlRelevanceScore(race: RaceSummary): number {
    const title = race.title || "";
    const id = race.id || "";
    const isKey = chamberSummary?.competitive_races?.some(t =>
      t === title || title.includes(t) || id.includes(t)
    );

    let ratingPriority = 4;
    if (race.forecast) {
      const r = race.forecast.rating.toLowerCase();
      if (r.includes("tossup") || r.includes("toss-up")) {
        ratingPriority = 0;
      } else if (r.includes("tilt")) {
        ratingPriority = 1;
      } else if (r.includes("lean")) {
        ratingPriority = 2;
      } else if (r.includes("likely")) {
        ratingPriority = 3;
      } else if (r.includes("safe")) {
        ratingPriority = 4;
      }
    }

    const winProb = race.forecast?.win_probability ?? 0.5;
    const closeness = Math.abs(winProb - 0.5);

    const keyWeight = isKey ? 0 : 1000;
    const ratingWeight = ratingPriority * 100;
    const closenessWeight = closeness * 10;

    return keyWeight + ratingWeight + closenessWeight;
  }

  function getHostname(urlString: string): string {
    try {
      return new URL(urlString).hostname.replace("www.", "");
    } catch (e) {
      return "Source Link";
    }
  }

  $: filteredRaces = aggregate.races
    .filter((race) => {
      if (selectedState && getRaceState(race) !== selectedState) return false;

      if (filterRating !== "all") {
        const rating = race.forecast.rating.toLowerCase();
        if (filterRating === "tossup" && !rating.includes("tossup")) return false;
        if (filterRating === "tilt" && !rating.startsWith("tilt_")) return false;
        if (filterRating === "lean" && !rating.startsWith("lean_")) return false;
        if (filterRating === "likely_safe" && !rating.startsWith("likely_") && !rating.startsWith("safe_")) return false;
      }

      if (filterParty !== "all") {
        const party = normalizeForecastParty(race.forecast.predicted_winner_party);
        if (filterParty !== party) return false;
      }

      return true;
    })
    .sort((a, b) => {
      if (sortBy === "state") {
        const stateA = getRaceState(a) || "";
        const stateB = getRaceState(b) || "";
        return stateA.localeCompare(stateB);
      }
      if (sortBy === "rating") {
        const indexA = ratingOrder.indexOf(a.forecast.rating);
        const indexB = ratingOrder.indexOf(b.forecast.rating);
        return indexA - indexB;
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
      if (sortBy === "dem_pickup") {
        const demProbA = a.forecast.party_probabilities?.Democratic ?? 0;
        const demProbB = b.forecast.party_probabilities?.Democratic ?? 0;
        return demProbB - demProbA;
      }
      if (sortBy === "gop_pickup") {
        const gopProbA = a.forecast.party_probabilities?.Republican ?? 0;
        const gopProbB = b.forecast.party_probabilities?.Republican ?? 0;
        return gopProbB - gopProbA;
      }
      if (sortBy === "competitiveness") {
        const diffA = Math.abs((a.forecast.win_probability ?? 0.5) - 0.5);
        const diffB = Math.abs((b.forecast.win_probability ?? 0.5) - 0.5);
        return diffA - diffB;
      }
      return getControlRelevanceScore(a) - getControlRelevanceScore(b);
    });

  $: sortedRaces = filteredRaces;

  $: keyRacesList = races.filter(r => {
    if (!isRaceInForecastTab(r, activeTab)) return false;
    const title = r.title || "";
    const id = r.id || "";
    return chamberSummary?.competitive_races?.some(t =>
      t === title || title.includes(t) || id.includes(t)
    );
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

  function oneDecimal(value?: number): string {
    if (value === undefined || value === null) return "n/a";
    return value.toFixed(1);
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

  <!-- Forecast Above-The-Fold Layout -->
  <div class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md space-y-6 animate-fade-in">
    <!-- Forecast Header -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-stroke/20 pb-4">
      <div class="space-y-1">
        <h2 class="text-2xl font-black text-content tracking-tight">
          2026 {activeTab === "house" ? "House" : activeTab === "senate" ? "Senate" : "Governor"} Forecast
        </h2>
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-content-subtle font-medium">
          <span>Method: <span class="font-bold text-content">{chamberSummary?.method || 'Static published SmarterVote projection'}</span></span>
          {#if chamberForecasts?.updated_at}
            <span class="w-1.5 h-1.5 rounded-full bg-stroke/60" />
            <span>Updated: <span class="font-bold text-content">{new Date(chamberForecasts.updated_at).toLocaleDateString()}</span></span>
          {/if}
        </div>
      </div>

      <div class="flex flex-col gap-1.5 items-start md:items-end">
        <!-- Control Status Badge -->
        <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm font-extrabold shadow-sm border
          {controlParty === 'Democratic' ? 'bg-blue-500/10 text-blue-700 border-blue-500/20 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-900/40' :
           controlParty === 'Republican' ? 'bg-red-500/10 text-red-700 border-red-500/20 dark:bg-red-950/40 dark:text-red-300 dark:border-red-900/40' :
           'bg-slate-500/10 text-slate-700 border-slate-500/20 dark:bg-slate-800/40 dark:text-slate-300 dark:border-slate-700/40'}">
          <span class="w-2.5 h-2.5 rounded-full
            {controlParty === 'Democratic' ? 'bg-blue-600 dark:bg-blue-500 animate-pulse' :
             controlParty === 'Republican' ? 'bg-red-600 dark:bg-red-500 animate-pulse' :
             'bg-slate-500 dark:bg-slate-400'}" />
          {#if controlParty === "Other"}
            No clear control projected
          {:else}
            {controlParty} control projected
            {#if chamberSummary?.control_probability}
              ({probability(chamberSummary.control_probability)})
            {/if}
          {/if}
        </span>

        <!-- VP Tie-break Note -->
        {#if activeTab === "senate" && chamberSummary?.vp_tiebreak_party}
          <span class="text-[10px] text-content-subtle font-semibold italic">
            Includes 50-50 tie-break with {chamberSummary.vp_tiebreak_party} Vice President
          </span>
        {/if}
      </div>
    </div>

    <!-- Control Probability and Seats Projection Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <!-- Control Probability Panel -->
      <div class="space-y-4">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold uppercase text-content-subtle tracking-wider font-semibold">Chamber Control Probabilities</span>
          {#if activeTab === "senate" && outcomeProbabilities?.tie_50_50}
            <span class="text-[10px] font-semibold text-red-600 dark:text-red-400 bg-red-500/5 px-2 py-0.5 rounded-md border border-red-500/10">
              50-50 Tie Probability: {probability(outcomeProbabilities.tie_50_50)}
            </span>
          {/if}
        </div>

        {#if outcomeProbabilities}
          {@const demProb = outcomeProbabilities.Democratic ?? 0}
          {@const gopProb = outcomeProbabilities.Republican ?? 0}
          {@const otherProb = outcomeProbabilities.Other ?? 0}
          <div class="space-y-3">
            <div class="h-8 rounded-xl overflow-hidden bg-surface-alt flex border border-stroke/60 relative shadow-inner">
              {#if demProb > 0}
                <div class="bg-blue-600 dark:bg-blue-500 transition-all duration-500 flex items-center justify-center font-black text-white text-xs" style="width: {demProb * 100}%" title="Democratic control probability: {probability(demProb)}">
                  {#if demProb > 0.15}
                    Democratic {probability(demProb)}
                  {/if}
                </div>
              {/if}
              {#if otherProb > 0}
                <div class="bg-slate-400 dark:bg-slate-500 transition-all duration-500 flex items-center justify-center font-black text-white text-xs" style="width: {otherProb * 100}%" title="Other control probability: {probability(otherProb)}">
                  {#if otherProb > 0.15}
                    Other {probability(otherProb)}
                  {/if}
                </div>
              {/if}
              {#if gopProb > 0}
                <div class="bg-red-600 dark:bg-red-500 transition-all duration-500 flex items-center justify-center font-black text-white text-xs ml-auto" style="width: {gopProb * 100}%" title="Republican control probability: {probability(gopProb)}">
                  {#if gopProb > 0.15}
                    Republican {probability(gopProb)}
                  {/if}
                </div>
              {/if}
            </div>

            <!-- Callout Note -->
            {#if activeTab === "senate" && outcomeProbabilities.tie_50_50}
              <div class="bg-surface-alt/40 border border-stroke/60 rounded-xl p-3 flex items-start gap-2.5">
                <span class="text-lg leading-none select-none mt-0.5">â„¹ï¸</span>
                <p class="text-xs text-content-muted leading-relaxed font-medium">
                  Republicans are favored because 50-50 outcomes are counted as Republican control under the VP tie-break assumption. This includes a <span class="font-extrabold text-content">{probability(outcomeProbabilities.tie_50_50)}</span> probability of a 50-50 tie.
                </p>
              </div>
            {/if}
          </div>
        {:else}
          <div class="p-4 border border-stroke border-dashed rounded-xl text-center text-xs text-content-subtle">
            Control probabilities are not available for this projection.
          </div>
        {/if}
      </div>

      <!-- Seats Projection Bar -->
      <div class="space-y-4">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold uppercase text-content-subtle tracking-wider font-semibold">Projected Seats</span>
          {#if expectedSeats}
            <span class="text-[10px] text-content-subtle font-semibold">
              Expected seats: D {oneDecimal(expectedSeats.Democratic)} | R {oneDecimal(expectedSeats.Republican)}
              {#if expectedSeats.Other} | Other {oneDecimal(expectedSeats.Other)}{/if}
            </span>
          {/if}
        </div>

        <div class="space-y-3">
          <div class="space-y-2">
            <div class="relative">
              <div class="h-8 rounded-xl overflow-hidden bg-surface-alt flex border border-stroke/60 shadow-inner">
                <!-- Dem segment -->
                <div class="bg-blue-600 dark:bg-blue-500 transition-all duration-500 flex items-center justify-center text-xs font-black text-white"
                     style="width: {((projectedSeats.Democratic ?? 0) / totalSeats) * 100}%">
                  {#if (projectedSeats.Democratic ?? 0) > (totalSeats * 0.12)}
                    D: {projectedSeats.Democratic}
                  {/if}
                </div>
                <!-- Other segment -->
                {#if projectedSeats.Other}
                  <div class="bg-slate-400 dark:bg-slate-500 transition-all duration-500 flex items-center justify-center text-xs font-black text-white"
                       style="width: {((projectedSeats.Other ?? 0) / totalSeats) * 100}%">
                    {projectedSeats.Other}
                  </div>
                {/if}
                <!-- Rep segment -->
                <div class="bg-red-600 dark:bg-red-500 transition-all duration-500 flex items-center justify-center text-xs font-black text-white ml-auto"
                     style="width: {((projectedSeats.Republican ?? 0) / totalSeats) * 100}%">
                  {#if (projectedSeats.Republican ?? 0) > (totalSeats * 0.12)}
                    R: {projectedSeats.Republican}
                  {/if}
                </div>
              </div>

              <!-- Threshold Marker Line -->
              <div class="absolute top-0 bottom-0 w-0.5 bg-yellow-500 dark:bg-yellow-400 z-10"
                   style="left: {(threshold / totalSeats) * 100}%">
                <span class="absolute bottom-full left-1/2 transform -translate-x-1/2 -translate-y-1 bg-yellow-500 dark:bg-yellow-400 text-[8px] font-black text-white dark:text-slate-950 px-1 py-0.5 rounded shadow-sm whitespace-nowrap animate-fade-in">
                  Majority ({threshold})
                </span>
              </div>

              <!-- Senate 50-50 Line -->
              {#if activeTab === "senate"}
                <div class="absolute top-0 bottom-0 w-0.5 bg-slate-400/80 dark:bg-slate-500/80 z-10"
                     style="left: 50%">
                  <span class="absolute top-full left-1/2 transform -translate-x-1/2 translate-y-1 bg-slate-500 text-[8px] font-black text-white px-1 py-0.5 rounded shadow-sm whitespace-nowrap animate-fade-in">
                    50-50 Split
                  </span>
                </div>
              {/if}
            </div>

            <div class="flex justify-between text-[10px] text-content-subtle px-1 pt-1.5 font-semibold">
              <span>Total: {totalSeats} seats</span>
              <span class="font-bold text-yellow-600 dark:text-yellow-400">Majority threshold: {threshold} seats</span>
            </div>
          </div>

          <!-- 50-50 tie-break warning/alert for Senate -->
          {#if activeTab === "senate" && projectedSeats.Democratic === 50 && projectedSeats.Republican === 50}
            <div class="bg-red-500/5 border border-red-500/20 rounded-xl p-2.5 text-center text-xs text-red-600 dark:text-red-400 font-bold flex items-center justify-center gap-2 animate-pulse">
              <span>âš ï¸</span>
              Projected 50-50 seat split. Republican control projected under the VP tie-break assumption.
            </div>
          {/if}
        </div>
      </div>
    </div>
  </div>

  <!-- Outlook & Analysis Section -->
  <section class="space-y-4">
    <div class="flex items-center justify-between border-b border-stroke/20 pb-2">
      <h3 class="text-base font-bold uppercase text-content tracking-wider">Outlook & Analysis</h3>
      <span class="text-xs text-content-subtle font-semibold">Structured assessment of the {activeTab === "house" ? "House" : activeTab === "senate" ? "Senate" : "Governor"} map</span>
    </div>

    {#if chamberSummary?.bottom_line || chamberSummary?.why_party_favored || chamberSummary?.opposing_party_path || chamberSummary?.key_uncertainty}
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Bottom Line -->
        {#if chamberSummary.bottom_line}
          <div class="bg-surface/80 border-2 border-blue-500/30 dark:border-blue-500/20 rounded-2xl p-5 shadow-sm relative overflow-hidden backdrop-blur-md">
            <div class="absolute top-0 right-0 w-24 h-24 bg-blue-500/5 dark:bg-blue-500/10 rounded-bl-full pointer-events-none" />
            <h4 class="text-xs font-black uppercase text-blue-600 dark:text-blue-400 tracking-widest mb-2 flex items-center gap-1.5">
              <span>ðŸŽ¯</span> The Bottom Line
            </h4>
            <p class="text-sm font-semibold text-content leading-relaxed">
              {chamberSummary.bottom_line}
            </p>
          </div>
        {/if}

        <!-- Why Favored -->
        {#if chamberSummary.why_party_favored}
          <div class="bg-surface/60 border border-stroke rounded-2xl p-5 shadow-sm backdrop-blur-md">
            <h4 class="text-xs font-black uppercase text-red-600 dark:text-red-400 tracking-widest mb-2 flex items-center gap-1.5">
              <span>ðŸ“ˆ</span> Why {chamberSummary.control_party === 'Democratic' ? 'Democrats' : 'Republicans'} Are Favored
            </h4>
            <p class="text-xs text-content-muted leading-relaxed font-medium font-semibold">
              {chamberSummary.why_party_favored}
            </p>
          </div>
        {/if}

        <!-- Opposing Path -->
        {#if chamberSummary.opposing_party_path}
          <div class="bg-surface/60 border border-stroke rounded-2xl p-5 shadow-sm backdrop-blur-md">
            <h4 class="text-xs font-black uppercase text-blue-600 dark:text-blue-400 tracking-widest mb-2 flex items-center gap-1.5">
              <span>ðŸ”„</span> {chamberSummary.control_party === 'Democratic' ? 'Republican' : 'Democratic'} Path to Control
            </h4>
            <p class="text-xs text-content-muted leading-relaxed font-medium font-semibold">
              {chamberSummary.opposing_party_path}
            </p>
          </div>
        {/if}

        <!-- Key Uncertainty -->
        {#if chamberSummary.key_uncertainty}
          <div class="bg-surface/60 border border-stroke rounded-2xl p-5 shadow-sm backdrop-blur-md">
            <h4 class="text-xs font-black uppercase text-yellow-600 dark:text-yellow-400 tracking-widest mb-2 flex items-center gap-1.5">
              <span>â“</span> Key Risk & Uncertainty
            </h4>
            <p class="text-xs text-content-muted leading-relaxed font-medium font-semibold">
              {chamberSummary.key_uncertainty}
            </p>
          </div>
        {/if}
      </div>
    {:else}
      <!-- Fallback narrative card -->
      <div class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md flex flex-col justify-between">
        <div>
          <p class="text-sm font-medium text-content leading-relaxed">
            {chamberNarrative || `Projections indicate a highly competitive cycle for the ${activeTab === 'governors' ? 'Governors' : activeTab === 'senate' ? 'Senate' : 'House'}.`}
          </p>
        </div>
      </div>
    {/if}

    <!-- Races That Matter Most -->
    {#if keyRacesList.length > 0}
      <div class="bg-surface-alt/20 border border-stroke/60 rounded-2xl p-5">
        <h4 class="text-xs font-black uppercase text-content-subtle tracking-wider mb-3">Races That Matter Most</h4>
        <div class="flex flex-wrap gap-2">
          {#each keyRacesList as race}
            {@const rating = race.forecast?.rating}
            {@const party = normalizeForecastParty(race.forecast?.predicted_winner_party)}
            <a href={browser ? raceHref(race.id) : undefined}
               class="inline-flex items-center gap-2 px-3 py-1.5 bg-surface hover:bg-surface-alt border border-stroke/80 rounded-xl transition-all shadow-sm">
              <span class="text-xs font-extrabold text-content">{race.state || race.title?.replace("2026 U.S. Senate election in ", "")}</span>
              {#if rating}
                <span class="w-1.5 h-1.5 rounded-full {party === 'Democratic' ? 'bg-blue-600 animate-pulse' : party === 'Republican' ? 'bg-red-600 animate-pulse' : 'bg-slate-400'}" />
                <span class="text-[10px] font-bold text-content-subtle">{formatRating(rating)}</span>
              {/if}
            </a>
          {/each}
        </div>
      </div>
    {/if}
  </section>

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
            Clear Map Filter: {selectedState} Ã—
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
                class="w-3.5 h-3.5 rounded block border border-blue-500/30 border-dashed" style="background-color: var(--color-holdover-d);"
              /> Dem Holdover
            </div>
            <div class="flex items-center gap-1.5 text-xs text-content-muted">
              <span
                class="w-3.5 h-3.5 rounded block border border-red-500/30 border-dashed" style="background-color: var(--color-holdover-r);"
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
          <span class={partyClass(controlParty)}>
            {controlParty === "Other" ? "No Clear Control" : `${controlParty} Control`}
          </span>
        </h3>

        <p class="mt-1 text-xs text-content-subtle font-medium">
          {chamberSummary?.threshold ?? aggregate.threshold} seats needed for majority
        </p>

        <!-- Seat Distribution Bar Chart -->
        <div class="mt-6 space-y-1.5">
          <div
            class="flex items-center justify-between text-xs font-bold text-content-muted"
          >
            <span>Democrat: {projectedSeats.Democratic ?? 0}</span>
            <span>Republican: {projectedSeats.Republican ?? 0}</span>
          </div>

          <div
            class="h-6 rounded-full overflow-hidden bg-surface-alt flex border border-stroke/60"
          >
            <div
              class="bg-blue-600 dark:bg-blue-500 transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner"
              style={`width: ${Math.min(
                100,
                  ((projectedSeats.Democratic ?? 0) /
                  aggregate.totalExpected) *
                  100
              )}%`}
              title="Democratic projected seats"
            >
              {#if (projectedSeats.Democratic ?? 0) > 20}
                {projectedSeats.Democratic}
              {/if}
            </div>
            {#if projectedSeats.Other}
              <div
                class="bg-slate-400 dark:bg-slate-500 transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner"
                style={`width: ${Math.min(
                  100,
                  ((projectedSeats.Other ?? 0) / aggregate.totalExpected) *
                    100
                )}%`}
                title="Other projected seats"
              >
                {projectedSeats.Other}
              </div>
            {/if}
            <div
              class="bg-red-600 dark:bg-red-500 transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner ml-auto"
              style={`width: ${Math.min(
                100,
                ((projectedSeats.Republican ?? 0) /
                  aggregate.totalExpected) *
                  100
              )}%`}
              title="Republican projected seats"
            >
              {#if (projectedSeats.Republican ?? 0) > 20}
                {projectedSeats.Republican}
              {/if}
            </div>
          </div>

          <div
            class="flex justify-between text-[10px] text-content-subtle px-1"
          >
            <span>Total: {aggregate.totalExpected}</span>
            <span>Majority Line: {chamberSummary?.threshold ?? aggregate.threshold}</span>
          </div>
          {#if outcomeProbabilities}
            <div class="mt-4 grid grid-cols-2 gap-2 text-xs">
              <div class="rounded-lg border border-blue-500/20 bg-blue-500/10 px-3 py-2">
                <div class="font-bold text-blue-700 dark:text-blue-300">
                  {probability(outcomeProbabilities.Democratic)}
                </div>
                <div class="text-[10px] text-content-subtle font-semibold uppercase tracking-wider">
                  Dem control
                </div>
              </div>
              <div class="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-right">
                <div class="font-bold text-red-700 dark:text-red-300">
                  {probability(outcomeProbabilities.Republican)}
                </div>
                <div class="text-[10px] text-content-subtle font-semibold uppercase tracking-wider">
                  GOP control
                </div>
              </div>
            </div>
          {/if}
          {#if expectedSeats}
            <p class="mt-3 text-[10px] text-content-subtle">
              Expected seats: D {oneDecimal(expectedSeats.Democratic)}, R {oneDecimal(expectedSeats.Republican)}
            </p>
          {/if}
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
                {projectedSeats[party] ?? 0}
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
          {showHoldovers ? "Hide List â–²" : "Show List â–¼"}
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
    <div class="px-5 py-5 border-b border-stroke/40 bg-surface-alt/10 space-y-4">
      <div class="flex flex-col md:flex-row justify-between gap-4">
        <!-- Pills Filter block -->
        <div class="space-y-2.5">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-xs font-bold text-content-subtle uppercase tracking-wider w-16">Rating:</span>
            {#each [
              { id: 'all', label: 'All Ratings' },
              { id: 'tossup', label: 'Toss-ups' },
              { id: 'tilt', label: 'Tilt' },
              { id: 'lean', label: 'Lean' },
              { id: 'likely_safe', label: 'Likely/Safe' }
            ] as pill}
              <button
                type="button"
                on:click={() => filterRating = pill.id}
                class="text-xs px-3 py-1.5 rounded-full font-bold transition-all border
                  {filterRating === pill.id ? 'bg-blue-600 text-white border-blue-600 dark:bg-blue-500 dark:border-blue-500' : 'bg-surface border-stroke hover:bg-surface-alt/50 text-content-muted'}"
              >
                {pill.label}
              </button>
            {/each}
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <span class="text-xs font-bold text-content-subtle uppercase tracking-wider w-16">Favored:</span>
            {#each [
              { id: 'all', label: 'All Parties' },
              { id: 'Democratic', label: 'Democratic' },
              { id: 'Republican', label: 'Republican' }
            ] as pill}
              <button
                type="button"
                on:click={() => filterParty = pill.id}
                class="text-xs px-3 py-1.5 rounded-full font-bold transition-all border
                  {filterParty === pill.id ?
                    (pill.id === 'Democratic' ? 'bg-blue-600 text-white border-blue-600 dark:bg-blue-500 dark:border-blue-500' : 'bg-red-600 text-white border-red-600 dark:bg-red-500 dark:border-red-500') :
                    'bg-surface border-stroke hover:bg-surface-alt/50 text-content-muted'}"
              >
                {pill.label}
              </button>
            {/each}
          </div>
        </div>

        <!-- Sort block -->
        <div class="flex flex-row md:flex-col md:items-end justify-between md:justify-start gap-4">
          <div class="flex items-center gap-2.5">
            <label for="sort-by" class="text-xs font-bold text-content-subtle uppercase tracking-wider">Sort by:</label>
            <select id="sort-by" bind:value={sortBy} class="text-xs bg-surface border border-stroke/60 rounded-xl px-3 py-1.5 text-content font-bold focus:outline-none focus:ring-1 focus:ring-blue-500">
              <option value="control_relevance">Most likely to decide control</option>
              <option value="competitiveness">Most competitive</option>
              <option value="dem_pickup">Highest Democratic pickup chance</option>
              <option value="gop_pickup">Highest Republican hold/pickup chance</option>
              <option value="probability">Win Probability</option>
              <option value="margin">Margin Estimate</option>
              <option value="state">State</option>
              <option value="rating">Rating</option>
            </select>
          </div>

          <div class="flex items-center gap-2.5 text-xs">
            {#if selectedState}
              <button
                type="button"
                on:click={clearStateFilter}
                class="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-bold bg-blue-50 dark:bg-blue-950/40 px-2.5 py-1 rounded-xl border border-blue-200/50"
              >
                State: {selectedState} Ã—
              </button>
            {/if}

            <span class="text-xs text-content-subtle font-extrabold bg-surface-alt px-2.5 py-1 rounded-xl border border-stroke/60">
              {filteredRaces.length} races
            </span>
          </div>
        </div>
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
            type="button"
            on:click={() => { clearStateFilter(); filterRating = 'all'; filterParty = 'all'; }}
            class="mt-3 text-xs text-blue-600 hover:underline dark:text-blue-400 font-semibold"
          >
            Clear all filters
          </button>
        {/if}
      </div>
    {:else}
      <!-- Responsive Card Feed -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4 bg-surface-alt/10">
        {#each sortedRaces as race (race.id)}
          {@const party = normalizeForecastParty(race.forecast.predicted_winner_party)}
          {@const rating = race.forecast.rating}
          {@const isExpanded = expandedRaceIds.has(race.id)}

          <article class="bg-surface border border-stroke/70 rounded-xl p-5 shadow-sm hover:border-blue-400/50 dark:hover:border-blue-500/50 transition-colors flex flex-col justify-between gap-4">
            <div class="space-y-4">
              <!-- Card Header: Title, Rating, and Details Link -->
              <div class="flex flex-col gap-1.5">
                <div class="flex items-start justify-between gap-2">
                  <a
                    href={browser ? raceHref(race.id) : undefined}
                    class="text-base font-extrabold text-content hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                  >
                    {race.title ?? race.id}
                  </a>
                  <a
                    href={browser ? raceHref(race.id) : undefined}
                    class="text-[10px] text-content-subtle hover:text-blue-600 dark:hover:text-blue-400 font-extrabold bg-surface border border-stroke/60 px-2 py-0.5 rounded-md transition-all whitespace-nowrap self-start"
                  >
                    Details â†’
                  </a>
                </div>
                <div class="flex flex-wrap items-center gap-1.5">
                  <span class="text-xs text-content-subtle font-medium">
                    {race.jurisdiction ?? race.state ?? race.office}
                  </span>
                  <span class="w-1 h-1 rounded-full bg-stroke/60" />
                  <span class={`inline-flex border rounded-full px-2 py-0.5 text-[10px] font-black leading-none ${ratingClass(rating)}`}>
                    {formatRating(rating)}
                  </span>
                </div>
              </div>

              <!-- Card Metrics Dashboard -->
              <div class="grid grid-cols-3 gap-2 bg-surface-alt/30 border border-stroke/40 rounded-xl p-3 text-center">
                <div class="flex flex-col justify-center border-r border-stroke/30 min-w-0 pr-1">
                  <span class="text-[9px] font-bold text-content-subtle uppercase tracking-wider">Projected</span>
                  <span class={`text-xs font-black mt-0.5 leading-tight break-words truncate ${partyClass(party)}`} title={race.forecast.predicted_winner_name || party}>
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
                  <span class="text-xs font-black mt-0.5 text-content tabular-nums">
                    {race.forecast.margin_estimate === undefined || race.forecast.margin_estimate === null
                      ? "n/a"
                      : `${race.forecast.margin_estimate > 0 ? '+' : ''}${race.forecast.margin_estimate.toFixed(1)}%`}
                  </span>
                </div>
              </div>

              <!-- D vs R Split details -->
              {#if race.forecast.party_probabilities}
                <div class="text-[10px] text-content-subtle flex justify-between font-bold px-1.5">
                  <span class="text-blue-600 dark:text-blue-400">Dem: {probability(race.forecast.party_probabilities.Democratic)}</span>
                  <span class="text-red-600 dark:text-red-400">GOP: {probability(race.forecast.party_probabilities.Republican)}</span>
                </div>
              {/if}

              <!-- Takeaway Text -->
              <div class="flex flex-col justify-center border-t border-stroke/20 pt-2.5">
                <span class="text-[9px] font-bold text-content-subtle uppercase tracking-wider mb-1">Key Takeaway</span>
                <p class="text-xs text-content-muted leading-relaxed font-medium">
                  {race.forecast.takeaway || (race.forecast.rationale ? race.forecast.rationale.split(/[.!?]/)[0] + "." : "No summary narrative available.")}
                </p>
              </div>
            </div>

            <!-- Card Accordion Toggle -->
            <div>
              <div class="flex items-center justify-between border-t border-stroke/10 pt-3">
                <button
                  type="button"
                  on:click={() => toggleExpand(race.id)}
                  class="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-bold flex items-center gap-1 focus:outline-none"
                >
                  <span class="inline-block transition-transform duration-200" style={isExpanded ? "transform: rotate(180deg);" : ""}>â–¼</span>
                  {isExpanded ? "Hide Analysis" : "Expand Analysis"}
                </button>

                <span class="text-[10px] text-content-subtle font-medium">
                  {race.forecast.based_on_poll_count} poll{race.forecast.based_on_poll_count === 1 ? "" : "s"} analyzed
                </span>
              </div>

              <!-- Expandable Drawer Content -->
              {#if isExpanded}
                <div class="mt-3 pt-3 border-t border-stroke/30 flex flex-col gap-3 text-xs bg-surface-alt/10 rounded-xl p-4 shadow-inner">
                  <!-- Full Rationale -->
                  <div>
                    <span class="font-bold text-content uppercase tracking-wider text-[9px] block mb-1">Full Assessment</span>
                    <p class="text-content-muted leading-relaxed font-medium whitespace-pre-wrap">{race.forecast.rationale}</p>
                  </div>

                  <!-- Key Drivers -->
                  {#if race.forecast.key_reasons && race.forecast.key_reasons.length > 0}
                    <div class="pt-2 border-t border-stroke/20">
                      <span class="font-bold text-content uppercase tracking-wider text-[9px] block mb-1">Key Drivers</span>
                      <ul class="list-disc list-inside space-y-1 text-content-muted font-medium pl-1">
                        {#each race.forecast.key_reasons as reason}
                          <li>{reason}</li>
                        {/each}
                      </ul>
                    </div>
                  {/if}

                  <!-- Uncertainty -->
                  {#if race.forecast.uncertainty}
                    <div class="pt-2 border-t border-stroke/20">
                      <span class="font-bold text-content uppercase tracking-wider text-[9px] block mb-1">Risk Factors & Uncertainty</span>
                      <p class="text-content-muted font-medium leading-relaxed">{race.forecast.uncertainty}</p>
                    </div>
                  {/if}

                  <!-- Source Links -->
                  {#if race.forecast.source_urls && race.forecast.source_urls.length > 0}
                    <div class="pt-2 border-t border-stroke/20">
                      <span class="font-bold text-content uppercase tracking-wider text-[9px] block mb-1">Source Documentation</span>
                      <div class="flex flex-wrap gap-1.5">
                        {#each race.forecast.source_urls as url}
                          <a href={url} target="_blank" rel="noopener noreferrer" class="inline-flex items-center text-[10px] text-blue-600 dark:text-blue-400 hover:underline bg-surface border border-stroke px-2 py-0.5 rounded-md truncate max-w-[180px]">
                            {getHostname(url)} â†—
                          </a>
                        {/each}
                      </div>
                    </div>
                  {/if}

                  <!-- Metadata -->
                  <div class="pt-2 border-t border-stroke/20 flex flex-wrap items-center justify-between gap-2 text-[9px] text-content-subtle font-bold">
                    {#if race.forecast.model}
                      <span>Model: {race.forecast.model}</span>
                    {/if}
                    {#if race.forecast.generated_at}
                      <span>Generated: {new Date(race.forecast.generated_at).toLocaleDateString()}</span>
                    {/if}
                  </div>
                </div>
              {/if}
            </div>
          </article>
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
