<script lang="ts">
  import { browser } from "$app/environment";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import ForecastElectoralMap from "$lib/components/forecast/ForecastElectoralMap.svelte";
  import ForecastHoldovers from "$lib/components/forecast/ForecastHoldovers.svelte";
  import ForecastKeyRaces from "$lib/components/forecast/ForecastKeyRaces.svelte";
  import ForecastMissingRaces from "$lib/components/forecast/ForecastMissingRaces.svelte";
  import ForecastOutlookAnalysis from "$lib/components/forecast/ForecastOutlookAnalysis.svelte";
  import ForecastProjectionSummary from "$lib/components/forecast/ForecastProjectionSummary.svelte";
  import ForecastRaceList from "$lib/components/forecast/ForecastRaceList.svelte";
  import ForecastRatingsBreakdown from "$lib/components/forecast/ForecastRatingsBreakdown.svelte";
  import ForecastSeatOutcomeChart from "$lib/components/forecast/ForecastSeatOutcomeChart.svelte";
  import ForecastSummaryCard from "$lib/components/forecast/ForecastSummaryCard.svelte";
  import ForecastTabNav from "$lib/components/forecast/ForecastTabNav.svelte";
  import ForecastUnavailable from "$lib/components/forecast/ForecastUnavailable.svelte";
  import type { ChamberForecasts, RaceSummary } from "$lib/types";
  import {
    aggregateForecasts,
    getMostLikelySeatOutcome,
    getRaceState,
    groupSeatDistribution,
    isRaceInForecastTab,
    parseForecastTab,
    resolveControlParty,
    FORECAST_RATING_ORDER,
    type ForecastTab,
  } from "$lib/utils/forecast";
  import {
    buildSeatOutcomeChart,
    buildStateMapData,
  } from "$lib/utils/forecastPresentation";

  const tabs: { id: ForecastTab; label: string }[] = [
    { id: "house", label: "House" },
    { id: "senate", label: "Senate" },
    { id: "governors", label: "Governors" },
  ];

  let activeTab: ForecastTab = "house";
  let selectedState: string | null = null;

  $: races = ($page.data.races as RaceSummary[] | undefined) ?? [];
  $: activeTab = browser
    ? parseForecastTab($page.url.searchParams.get("tab"))
    : "house";
  $: selectedState = browser
    ? $page.url.searchParams.get("state") || null
    : null;
  $: aggregate = aggregateForecasts(races, activeTab);

  $: chamberForecasts = $page.data.chamberForecasts as
    | ChamberForecasts
    | undefined;
  $: chamberSummary = chamberForecasts?.chambers?.[activeTab];
  $: chamberNarrative =
    chamberSummary?.narrative || chamberForecasts?.[activeTab] || "";

  $: seatBuckets = groupSeatDistribution(
    chamberSummary?.seat_distribution ?? {},
    activeTab,
  );
  $: seatOutcomeChart = buildSeatOutcomeChart(
    chamberSummary?.seat_distribution ?? {},
    chamberSummary?.threshold ?? 51,
  );

  $: projectedSeats = chamberSummary?.projected_seats ?? aggregate.projected;
  $: expectedSeats = chamberSummary?.expected_seats;
  $: outcomeProbabilities = chamberSummary?.outcome_probabilities;
  $: totalSeats = chamberSummary?.total_seats ?? aggregate.totalExpected;
  $: threshold = chamberSummary?.threshold ?? aggregate.threshold;
  $: controlParty = resolveControlParty(activeTab, chamberSummary, aggregate);

  // Active states + per-state race counts for the map click handler
  $: activeStates = new Set(
    races
      .filter((r) => isRaceInForecastTab(r, activeTab))
      .map(getRaceState)
      .filter(Boolean) as string[],
  );
  $: stateRaceCounts = races
    .filter((race) => isRaceInForecastTab(race, activeTab))
    .reduce<Record<string, number>>((counts, race) => {
      const state = getRaceState(race);
      if (state) counts[state] = (counts[state] ?? 0) + 1;
      return counts;
    }, {});

  // Dynamic colors and tooltips for the map
  $: stateMapData = buildStateMapData(races, activeTab);
  $: stateColors = stateMapData.colors;
  $: stateTooltips = stateMapData.tooltips;

  function handleStateClick(stateName: string) {
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

  $: keyRacesList = races.filter((r) => {
    if (!isRaceInForecastTab(r, activeTab)) return false;
    const title = r.title || "";
    const id = r.id || "";
    return chamberSummary?.competitive_races?.some(
      (t) => t === title || title.includes(t) || id.includes(t),
    );
  });

  $: filteredMissingRaces = selectedState
    ? aggregate.missingForecasts.filter(
        (r) => getRaceState(r) === selectedState,
      )
    : aggregate.missingForecasts;

  function clearStateFilter() {
    setUrlState(activeTab, null);
  }

  $: mostLikelyOutcome = getMostLikelySeatOutcome(
    chamberSummary?.seat_distribution ?? {},
  );
</script>

<svelte:head>
  <title>2026 Election Forecasts — Smarter.vote</title>
  <meta
    name="description"
    content="AI-powered forecasts and interactive maps for 2026 House, Senate, and Governor races. See win probabilities, polling data, and prediction market signals."
  />
  <link rel="canonical" href="https://smarter.vote/forecast/" />
  <meta property="og:type" content="article" />
  <meta property="og:url" content="https://smarter.vote/forecast/" />
  <meta property="og:title" content="2026 Election Forecasts — Smarter.vote" />
  <meta
    property="og:description"
    content="AI-powered forecasts and interactive maps for 2026 House, Senate, and Governor races. See win probabilities, polling data, and prediction market signals."
  />
  <meta property="og:image" content="https://smarter.vote/og-image.png" />
  <meta property="twitter:card" content="summary_large_image" />
  <meta property="twitter:url" content="https://smarter.vote/forecast/" />
  <meta
    property="twitter:title"
    content="2026 Election Forecasts — Smarter.vote"
  />
  <meta
    property="twitter:description"
    content="AI-powered forecasts and interactive maps for 2026 House, Senate, and Governor races. See win probabilities, polling data, and prediction market signals."
  />
  <meta property="twitter:image" content="https://smarter.vote/og-image.png" />
</svelte:head>

<div class="forecast-page max-w-7xl mx-auto px-4 py-8 sm:py-10 space-y-8">
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
          Nonpartisan model projections, interactive maps, and structured
          analysis for the 2026 House, Senate, and Governor races.
        </p>
      </div>
      <div
        class="text-xs text-content-subtle border border-stroke/80 bg-surface-alt/40 backdrop-blur-md px-3 py-2 rounded-xl flex items-center gap-1.5 self-start md:self-auto"
      >
        <span class="relative flex h-2 w-2">
          <span
            class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"
          ></span>
          <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"
          ></span>
        </span>
        Model status: Live
      </div>
    </div>
  </header>

  {#if (!races || races.length === 0) && (!chamberForecasts || !chamberForecasts.chambers)}
    <ForecastUnavailable />
  {:else}
    <ForecastTabNav {tabs} {activeTab} onSelect={setActiveTab} />

    <ForecastSummaryCard
      {activeTab}
      {controlParty}
      controlProbability={chamberSummary?.control_probability}
      vpTiebreakParty={chamberSummary?.vp_tiebreak_party}
      {mostLikelyOutcome}
      tossupCount={chamberSummary?.tossup_count ?? 0}
      competitiveRaceCount={chamberSummary?.competitive_race_count ?? 0}
      {outcomeProbabilities}
      {projectedSeats}
      {totalSeats}
      {threshold}
      narrative={chamberNarrative}
      updatedAt={chamberForecasts?.updated_at}
    />

    <!-- Interactive Map & Statistics Dashboard Grid -->
    <section
      class="grid grid-cols-1 lg:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.7fr)] gap-6 items-stretch"
    >
      <ForecastElectoralMap
        {activeTab}
        {activeStates}
        {selectedState}
        {stateRaceCounts}
        {stateColors}
        {stateTooltips}
        onStateClick={handleStateClick}
        onClearFilter={clearStateFilter}
      />

      <!-- Stats Panel Column -->
      <div class="space-y-6 h-full flex flex-col">
        <ForecastProjectionSummary
          label={aggregate.label}
          {controlParty}
          {threshold}
          {projectedSeats}
          totalExpected={aggregate.totalExpected}
          {outcomeProbabilities}
          {expectedSeats}
          netChange={aggregate.netChange}
        />

        {#if chamberSummary?.seat_distribution && Object.keys(chamberSummary.seat_distribution).length > 0}
          <ForecastSeatOutcomeChart
            {seatBuckets}
            sortedOutcomes={seatOutcomeChart.outcomes}
            maxProbability={seatOutcomeChart.maxProbability}
            svgData={seatOutcomeChart.svgData}
          />
        {/if}
      </div>
    </section>

    <ForecastRatingsBreakdown
      ratingOrder={FORECAST_RATING_ORDER}
      ratingCounts={aggregate.ratingCounts}
    />

    <ForecastKeyRaces races={keyRacesList} />

    <ForecastOutlookAnalysis {activeTab} {chamberSummary} {chamberNarrative} />

    <ForecastRaceList
      races={aggregate.races}
      {activeTab}
      {selectedState}
      {chamberSummary}
      onClearStateFilter={clearStateFilter}
    />

    <ForecastMissingRaces races={filteredMissingRaces} {activeTab} />

    <ForecastHoldovers {activeTab} holdovers={aggregate.holdovers} />
  {/if}
</div>

<style lang="postcss">
  /* :global() is required here: buttons/selects for this page now live inside
     child components (forecast/*.svelte), so a plain scoped selector would no
     longer match them. */
  .forecast-page :global(button),
  .forecast-page :global(select) {
    @apply min-h-11;
  }
</style>
