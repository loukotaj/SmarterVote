<script lang="ts">
  import { browser } from "$app/environment";
  import type { RaceSummary } from "$lib/types";
  import { formatRating, getRaceState, raceHref } from "$lib/utils/forecast";
  import { probability, ratingClass } from "$lib/utils/forecastPresentation";

  export let races: RaceSummary[];

  let keyRacesContainer: HTMLDivElement;
  function scrollKeyRaces(dir: number) {
    keyRacesContainer?.scrollBy({ left: dir * 320, behavior: "smooth" });
  }
</script>

{#if races.length > 0}
  <section class="space-y-4">
    <div
      class="flex items-center justify-between border-b border-stroke/20 pb-2"
    >
      <h3 class="text-base font-bold uppercase text-content tracking-wider">
        Races That Matter Most
      </h3>
      <div class="flex items-center gap-2">
        <span
          class="text-xs text-content-subtle font-semibold hidden sm:inline"
        >
          Key battlegrounds driving chamber control
        </span>
        <button
          on:click={() => scrollKeyRaces(-1)}
          class="h-11 w-11 rounded-lg border border-stroke/60 bg-surface hover:bg-surface-alt flex items-center justify-center text-content-subtle hover:text-content transition-colors"
          aria-label="Scroll left"
        >
          <svg
            class="w-4 h-4"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M15 19l-7-7 7-7"
            />
          </svg>
        </button>
        <button
          on:click={() => scrollKeyRaces(1)}
          class="h-11 w-11 rounded-lg border border-stroke/60 bg-surface hover:bg-surface-alt flex items-center justify-center text-content-subtle hover:text-content transition-colors"
          aria-label="Scroll right"
        >
          <svg
            class="w-4 h-4"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M9 5l7 7-7 7"
            />
          </svg>
        </button>
      </div>
    </div>

    <div
      bind:this={keyRacesContainer}
      class="flex gap-4 overflow-x-auto pb-3 scroll-smooth snap-x snap-mandatory hide-scrollbar"
      style="-ms-overflow-style: none; scrollbar-width: none;"
    >
      {#each races as race}
        {@const rating = race.forecast?.rating}
        {@const ratingBorderColor = rating
          ? rating.endsWith("_d")
            ? "border-l-blue-500"
            : rating.endsWith("_r")
              ? "border-l-red-500"
              : "border-l-yellow-500"
          : "border-l-slate-400"}
        <div
          class={`snap-start shrink-0 w-[300px] bg-surface border border-stroke rounded-xl p-4 shadow-sm hover:shadow-md transition-all border-l-[3px] ${ratingBorderColor}`}
        >
          <div class="flex items-center justify-between mb-2">
            <a
              href={browser ? raceHref(race.id) : undefined}
              class="inline-flex min-h-11 items-center font-black text-sm text-content hover:text-blue-600 dark:hover:text-blue-400 truncate"
            >
              {getRaceState(race) || race.title}
            </a>
            {#if rating}
              <span
                class={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full border shrink-0 ml-2 ${ratingClass(
                  rating,
                )}`}
              >
                {formatRating(rating)}
              </span>
            {/if}
          </div>

          {#if race.forecast}
            <div class="flex items-center gap-3 mb-2">
              <span class="text-xs font-bold text-content tabular-nums">
                {probability(race.forecast.win_probability)} win
              </span>
              {#if race.forecast.margin_estimate !== undefined && race.forecast.margin_estimate !== null}
                <span
                  class="text-[10px] text-content-subtle font-semibold tabular-nums"
                >
                  {race.forecast.margin_estimate > 0
                    ? "+"
                    : ""}{race.forecast.margin_estimate.toFixed(1)}% margin
                </span>
              {/if}
            </div>
          {/if}

          <p
            class="text-[11px] text-content-muted leading-relaxed font-medium line-clamp-2"
          >
            {race.forecast?.takeaway ||
              race.forecast?.rationale?.split(/[.!?]/)[0] + "." ||
              "No takeaway available."}
          </p>

          <div class="mt-3 pt-2 border-t border-stroke/30">
            <a
              href={browser ? raceHref(race.id) : undefined}
              class="inline-flex min-h-11 items-center text-xs text-blue-600 dark:text-blue-400 font-bold hover:underline"
            >
              View Details &rarr;
            </a>
          </div>
        </div>
      {/each}
    </div>
  </section>
{/if}
