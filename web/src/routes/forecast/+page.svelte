<script lang="ts">
  import { page } from "$app/stores";
  import TabButton from "$lib/components/TabButton.svelte";
  import type { ForecastRating, RaceSummary } from "$lib/types";
  import {
    aggregateForecasts,
    formatNet,
    formatRating,
    normalizeForecastParty,
    type ForecastTab,
  } from "$lib/utils/forecast";

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
    "other",
  ];

  let activeTab: ForecastTab = "house";

  $: races = ($page.data.races as RaceSummary[] | undefined) ?? [];
  $: aggregate = aggregateForecasts(races, activeTab);
  $: controlParty =
    (aggregate.projected.Democratic ?? 0) >= aggregate.threshold
      ? "Democratic"
      : (aggregate.projected.Republican ?? 0) >= aggregate.threshold
      ? "Republican"
      : "No clear control";

  function partyClass(party: string): string {
    if (party === "Democratic") return "text-blue-700 dark:text-blue-300";
    if (party === "Republican") return "text-red-700 dark:text-red-300";
    return "text-content-muted";
  }

  function ratingClass(rating: ForecastRating): string {
    if (rating.endsWith("_d"))
      return "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-200 dark:border-blue-800";
    if (rating.endsWith("_r"))
      return "bg-red-50 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-200 dark:border-red-800";
    return "bg-surface-alt text-content-muted border-stroke";
  }

  function probability(value?: number): string {
    if (value === undefined || value === null) return "n/a";
    return `${Math.round(value * 100)}%`;
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
    content="Informational AI forecasts for 2026 House, Senate, and governor races."
  />
</svelte:head>

<div class="max-w-7xl mx-auto px-4 py-8 sm:py-10">
  <header class="mb-6">
    <h1 class="text-3xl sm:text-4xl font-bold text-content tracking-tight">
      Forecasts
    </h1>
    <p class="mt-2 text-sm sm:text-base text-content-muted max-w-3xl">
      Informational AI estimates based on published Smarter.vote race data.
      Forecasts are not endorsements and should be checked against the linked
      race sources.
    </p>
  </header>

  <div class="border-b border-stroke mb-6 flex gap-1 overflow-x-auto">
    {#each tabs as tab}
      <TabButton
        active={activeTab === tab.id}
        onClick={() => (activeTab = tab.id)}
      >
        {tab.label}
      </TabButton>
    {/each}
  </div>

  <section
    class="grid grid-cols-1 lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)] gap-6 mb-8"
  >
    <div class="bg-surface border border-stroke rounded-lg p-5">
      <div
        class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4"
      >
        <div>
          <p
            class="text-xs font-semibold uppercase text-content-subtle tracking-wide"
          >
            {aggregate.label} control
          </p>
          <h2 class="mt-2 text-2xl font-bold text-content">
            <span class={partyClass(controlParty)}>{controlParty}</span>
          </h2>
          <p class="mt-1 text-sm text-content-muted">
            {aggregate.threshold} needed for control
          </p>
        </div>
        <div class="grid grid-cols-3 gap-3 min-w-0">
          {#each controlParties as party}
            <div
              class="bg-surface-alt rounded-lg px-3 py-2 text-center min-w-0"
            >
              <div class={`text-xl font-bold ${partyClass(party)}`}>
                {aggregate.projected[party] ?? 0}
              </div>
              <div class="text-[11px] text-content-subtle truncate">
                {party}
              </div>
              <div class="text-[11px] text-content-subtle tabular-nums">
                {formatNet(aggregate.netChange[party] ?? 0)}
              </div>
            </div>
          {/each}
        </div>
      </div>

      <div
        class="mt-6 h-5 rounded-full overflow-hidden bg-surface-alt flex border border-stroke"
      >
        <div
          class="bg-blue-600"
          style={`width: ${Math.min(
            100,
            ((aggregate.projected.Democratic ?? 0) / aggregate.totalExpected) *
              100
          )}%`}
          title="Democratic projected seats"
        />
        <div
          class="bg-red-600"
          style={`width: ${Math.min(
            100,
            ((aggregate.projected.Republican ?? 0) / aggregate.totalExpected) *
              100
          )}%`}
          title="Republican projected seats"
        />
        <div
          class="bg-gray-500"
          style={`width: ${Math.min(
            100,
            ((aggregate.projected.Other ?? 0) / aggregate.totalExpected) * 100
          )}%`}
          title="Other projected seats"
        />
      </div>

      <p class="mt-3 text-xs text-content-subtle">
        {aggregate.races.length} races with forecasts, {aggregate
          .missingForecasts.length} published races missing forecasts.
      </p>
    </div>

    <div class="bg-surface border border-stroke rounded-lg p-5">
      <p
        class="text-xs font-semibold uppercase text-content-subtle tracking-wide mb-4"
      >
        Ratings
      </p>
      <div class="grid grid-cols-2 sm:grid-cols-5 lg:grid-cols-2 gap-2">
        {#each ratingOrder as rating}
          <div class={`border rounded-lg px-3 py-2 ${ratingClass(rating)}`}>
            <div class="text-xs font-medium">{formatRating(rating)}</div>
            <div class="text-lg font-semibold">
              {aggregate.ratingCounts[rating] ?? 0}
            </div>
          </div>
        {/each}
      </div>
    </div>
  </section>

  <section class="bg-surface border border-stroke rounded-lg overflow-hidden">
    <div
      class="px-4 py-3 border-b border-stroke flex items-center justify-between gap-3"
    >
      <h2 class="text-base font-semibold text-content">Competitive Races</h2>
      <span class="text-xs text-content-subtle"
        >{aggregate.races.length} forecasted</span
      >
    </div>

    {#if aggregate.races.length === 0}
      <div class="p-8 text-center text-content-muted">
        No published {aggregate.label.toLowerCase()} forecasts yet.
      </div>
    {:else}
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="bg-surface-alt text-content-subtle">
            <tr>
              <th class="text-left font-semibold px-4 py-3">Race</th>
              <th class="text-left font-semibold px-4 py-3">Rating</th>
              <th class="text-left font-semibold px-4 py-3">Projected Winner</th
              >
              <th class="text-right font-semibold px-4 py-3">Win Prob.</th>
              <th class="text-right font-semibold px-4 py-3">Margin</th>
              <th class="text-left font-semibold px-4 py-3">Basis</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-stroke">
            {#each aggregate.races.slice(0, 80) as race}
              {@const party = normalizeForecastParty(
                race.forecast.predicted_winner_party
              )}
              <tr class="hover:bg-surface-alt/50">
                <td class="px-4 py-3 min-w-[240px]">
                  <a
                    href={raceHref(race.id)}
                    class="font-medium text-content hover:text-blue-600"
                  >
                    {race.title ?? race.id}
                  </a>
                  <div class="text-xs text-content-subtle mt-0.5">
                    {race.jurisdiction ?? race.state ?? race.office}
                  </div>
                </td>
                <td class="px-4 py-3">
                  <span
                    class={`inline-flex border rounded-full px-2 py-0.5 text-xs font-medium ${ratingClass(
                      race.forecast.rating
                    )}`}
                  >
                    {formatRating(race.forecast.rating)}
                  </span>
                </td>
                <td class="px-4 py-3">
                  <span class={partyClass(party)}
                    >{race.forecast.predicted_winner_name ??
                      race.forecast.predicted_winner_party ??
                      "Unknown"}</span
                  >
                  <div class="text-xs text-content-subtle">
                    {race.forecast.predicted_winner_party ?? "No party"}
                  </div>
                </td>
                <td class="px-4 py-3 text-right tabular-nums"
                  >{probability(race.forecast.win_probability)}</td
                >
                <td class="px-4 py-3 text-right tabular-nums">
                  {race.forecast.margin_estimate === undefined ||
                  race.forecast.margin_estimate === null
                    ? "n/a"
                    : `${race.forecast.margin_estimate.toFixed(1)} pts`}
                </td>
                <td class="px-4 py-3 max-w-xs">
                  <div class="text-content-muted">
                    {race.forecast.rationale}
                  </div>
                  <div class="text-xs text-content-subtle mt-1">
                    {race.forecast.based_on_poll_count} poll{race.forecast
                      .based_on_poll_count === 1
                      ? ""
                      : "s"}
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>
</div>
