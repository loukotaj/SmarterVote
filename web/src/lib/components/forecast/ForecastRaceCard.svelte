<script lang="ts">
  import { browser } from "$app/environment";
  import { isExternalUrl } from "$lib/utils/url";
  import type { ForecastRace } from "$lib/utils/forecast";
  import { raceDisplayTitle } from "$lib/utils/raceTitle";
  import {
    formatRating,
    normalizeForecastParty,
    raceHref,
  } from "$lib/utils/forecast";
  import {
    getHostname,
    marketAsOf,
    marketSignalTarget,
    marketSpread,
    partyClass,
    probability,
    probabilityOneDecimal,
    ratingClass,
  } from "$lib/utils/forecastPresentation";
  import ForecastEvidenceLineage from "./ForecastEvidenceLineage.svelte";

  export let race: ForecastRace;
  export let isExpanded: boolean;
  export let onToggleExpand: () => void;

  $: party = normalizeForecastParty(
    race.forecast.predicted_winner_party,
    race.forecast.party_probabilities,
    race.candidates,
  );
  $: rating = race.forecast.rating;
</script>

<article
  class="bg-surface border border-stroke/70 rounded-xl p-5 shadow-sm hover:border-blue-400/50 dark:hover:border-blue-500/50 transition-colors flex flex-col justify-between gap-4"
>
  <div class="space-y-4">
    <!-- Card Header: Title, Rating, and Details Link -->
    <div class="flex flex-col gap-1.5">
      <div class="flex items-start justify-between gap-2">
        <a
          href={browser ? raceHref(race.id) : undefined}
          class="text-base font-extrabold text-content hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
        >
          {raceDisplayTitle(race)}
        </a>
        <a
          href={browser ? raceHref(race.id) : undefined}
          class="text-[10px] text-content-subtle hover:text-blue-600 dark:hover:text-blue-400 font-extrabold bg-surface border border-stroke/60 px-2 py-0.5 rounded-md transition-all whitespace-nowrap self-start"
        >
          Details ->
        </a>
      </div>
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="text-xs text-content-subtle font-medium">
          {race.jurisdiction ?? race.state ?? race.office}
        </span>
        <span class="w-1 h-1 rounded-full bg-stroke/60"></span>
        <span
          class={`inline-flex border rounded-full px-2 py-0.5 text-[10px] font-black leading-none ${ratingClass(
            rating,
          )}`}
        >
          {formatRating(rating)}
        </span>
      </div>
    </div>

    <!-- Card Metrics Dashboard -->
    <div
      class="grid grid-cols-3 gap-2 bg-surface-alt/30 border border-stroke/40 rounded-xl p-3 text-center"
    >
      <div
        class="flex flex-col justify-center border-r border-stroke/30 min-w-0 pr-1"
      >
        <span
          class="text-[9px] font-bold text-content-subtle uppercase tracking-wider"
          >Projected</span
        >
        <span
          class={`text-xs font-black mt-0.5 leading-tight break-words truncate ${partyClass(
            party,
          )}`}
          title={race.forecast.predicted_winner_name || party}
        >
          {race.forecast.predicted_winner_name || party}
        </span>
      </div>
      <div class="flex flex-col justify-center border-r border-stroke/30">
        <span
          class="text-[9px] font-bold text-content-subtle uppercase tracking-wider"
          >Win Prob.</span
        >
        <span class="text-xs font-black mt-0.5 text-content tabular-nums">
          {probability(race.forecast.win_probability)}
        </span>
      </div>
      <div class="flex flex-col justify-center pl-1">
        <span
          class="text-[9px] font-bold text-content-subtle uppercase tracking-wider"
          >Est. Margin</span
        >
        <span class="text-xs font-black mt-0.5 text-content tabular-nums">
          {race.forecast.margin_estimate === undefined ||
          race.forecast.margin_estimate === null
            ? "n/a"
            : `${
                race.forecast.margin_estimate > 0 ? "+" : ""
              }${race.forecast.margin_estimate.toFixed(1)}%`}
        </span>
      </div>
    </div>

    <!-- D vs R Split details -->
    {#if race.forecast.party_probabilities}
      <div
        class="text-[10px] text-content-subtle flex justify-between font-bold px-1.5"
      >
        <span class="text-blue-600 dark:text-blue-400"
          >Dem: {probability(
            race.forecast.party_probabilities.Democratic,
          )}</span
        >
        <span class="text-red-600 dark:text-red-400"
          >GOP: {probability(
            race.forecast.party_probabilities.Republican,
          )}</span
        >
      </div>
    {/if}

    <!-- Takeaway Text -->
    <div class="flex flex-col justify-center border-t border-stroke/20 pt-2.5">
      <span
        class="text-[9px] font-bold text-content-subtle uppercase tracking-wider mb-1"
        >Key Takeaway</span
      >
      <p class="text-xs text-content-muted leading-relaxed font-medium">
        {race.forecast.takeaway ||
          (race.forecast.rationale
            ? race.forecast.rationale.split(/[.!?]/)[0] + "."
            : "No summary narrative available.")}
      </p>
    </div>
  </div>

  <!-- Card Accordion Toggle -->
  <div>
    <div
      class="flex items-center justify-between border-t border-stroke/10 pt-3"
    >
      <button
        type="button"
        on:click={onToggleExpand}
        class="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-bold flex items-center gap-1 focus:outline-none"
      >
        <span
          class="inline-block transition-transform duration-200"
          style={isExpanded ? "transform: rotate(180deg);" : ""}>v</span
        >
        {isExpanded ? "Hide Analysis" : "Expand Analysis"}
      </button>

      <span class="text-[10px] text-content-subtle font-medium">
        {race.forecast.based_on_poll_count} poll{race.forecast
          .based_on_poll_count === 1
          ? ""
          : "s"} analyzed
      </span>
    </div>

    <!-- Expandable Drawer Content -->
    {#if isExpanded}
      <div
        class="mt-3 pt-3 border-t border-stroke/30 flex flex-col gap-3 text-xs bg-surface-alt/10 rounded-xl p-4 shadow-inner"
      >
        <!-- Full Rationale -->
        <div>
          <span
            class="font-bold text-content uppercase tracking-wider text-[9px] block mb-1"
            >Full Assessment</span
          >
          <p
            class="text-content-muted leading-relaxed font-medium whitespace-pre-wrap"
          >
            {race.forecast.rationale}
          </p>
        </div>

        <!-- Key Drivers -->
        {#if race.forecast.key_reasons && race.forecast.key_reasons.length > 0}
          <div class="pt-2 border-t border-stroke/20">
            <span
              class="font-bold text-content uppercase tracking-wider text-[9px] block mb-1"
              >Key Drivers</span
            >
            <ul
              class="list-disc list-inside space-y-1 text-content-muted font-medium pl-1"
            >
              {#each race.forecast.key_reasons as reason}
                <li>{reason}</li>
              {/each}
            </ul>
          </div>
        {/if}

        <!-- Uncertainty -->
        {#if race.forecast.uncertainty}
          <div class="pt-2 border-t border-stroke/20">
            <span
              class="font-bold text-content uppercase tracking-wider text-[9px] block mb-1"
              >Risk Factors & Uncertainty</span
            >
            <p class="text-content-muted font-medium leading-relaxed">
              {race.forecast.uncertainty}
            </p>
          </div>
        {/if}

        {#if race.forecast.market_signals && race.forecast.market_signals.length > 0}
          <div class="pt-2 border-t border-stroke/20">
            <div class="flex items-center justify-between gap-2 mb-2">
              <span
                class="font-bold text-content uppercase tracking-wider text-[9px] block"
                >Kalshi Market Signals</span
              >
              <span class="text-[9px] text-content-subtle font-bold"
                >{race.forecast.market_signals.length} market{race.forecast
                  .market_signals.length === 1
                  ? ""
                  : "s"}</span
              >
            </div>
            <div class="grid gap-2">
              {#each race.forecast.market_signals as signal}
                <div
                  class="rounded-lg border border-stroke/60 bg-surface px-3 py-2"
                >
                  <div
                    class="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between"
                  >
                    <div>
                      <span class="block text-xs font-bold text-content"
                        >{marketSignalTarget(signal)}</span
                      >
                      <span
                        class="block text-[10px] text-content-subtle leading-snug"
                        >{signal.title}</span
                      >
                    </div>
                    <div
                      class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-content-subtle sm:justify-end"
                    >
                      <span class="font-bold text-content"
                        >{probabilityOneDecimal(
                          signal.implied_probability,
                        )}</span
                      >
                      {#if marketSpread(signal)}
                        <span>{marketSpread(signal)}</span>
                      {/if}
                      <span class="capitalize"
                        >{signal.confidence} confidence</span
                      >
                      {#if marketAsOf(signal.as_of)}
                        <span>As of {marketAsOf(signal.as_of)}</span>
                      {/if}
                      {#if isExternalUrl(signal.url)}
                        <a
                          href={signal.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          class="font-bold text-blue-600 hover:underline dark:text-blue-400"
                          >Kalshi</a
                        >
                      {/if}
                    </div>
                  </div>
                </div>
              {/each}
            </div>
          </div>
        {/if}

        <!-- Per-claim Evidence Attribution -->
        <ForecastEvidenceLineage entries={race.forecast.evidence_lineage} />

        <!-- Source Links -->
        {#if race.forecast.source_urls && race.forecast.source_urls.length > 0}
          <div class="pt-2 border-t border-stroke/20">
            <span
              class="font-bold text-content uppercase tracking-wider text-[9px] block mb-1"
              >Forecast sources</span
            >
            <div class="flex flex-wrap gap-1.5">
              {#each race.forecast.source_urls as url}
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  class="inline-flex items-center text-[10px] text-blue-600 dark:text-blue-400 hover:underline bg-surface border border-stroke px-2 py-0.5 rounded-md truncate max-w-[180px]"
                >
                  {getHostname(url)} ->
                </a>
              {/each}
            </div>
          </div>
        {/if}

        <!-- Metadata -->
        <div
          class="pt-2 border-t border-stroke/20 flex flex-wrap items-center justify-between gap-2 text-[9px] text-content-subtle font-bold"
        >
          {#if race.forecast.model}
            <span>Model: {race.forecast.model}</span>
          {/if}
          {#if race.forecast.generated_at}
            <span
              >Generated: {new Date(
                race.forecast.generated_at,
              ).toLocaleDateString()}</span
            >
          {/if}
        </div>
      </div>
    {/if}
  </div>
</article>
