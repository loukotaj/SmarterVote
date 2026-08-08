<script lang="ts">
  import { browser } from "$app/environment";
  import type { RaceSummary } from "$lib/types";
  import {
    fallbackPartyForRace,
    raceHref,
    type ForecastTab,
  } from "$lib/utils/forecast";
  import { partyClass } from "$lib/utils/forecastPresentation";

  export let races: RaceSummary[];
  export let activeTab: ForecastTab;
</script>

{#if races.length > 0}
  <section
    class="bg-surface border border-stroke rounded-2xl shadow-sm overflow-hidden opacity-85"
  >
    <div
      class="px-5 py-4 border-b border-stroke/40 flex items-center justify-between bg-surface-alt/10"
    >
      <div>
        <h2 class="text-base font-bold text-content-muted">
          Unforecasted Races ({races.length})
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
          {#each races as race}
            {@const fallback = fallbackPartyForRace(race, activeTab)}
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
                    {fallback} (Estimated)
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
