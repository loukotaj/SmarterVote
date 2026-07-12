<script lang="ts">
  import RaceCard from "$lib/components/RaceCard.svelte";
  import type { RaceSummary } from "$lib/types";
  export let races: RaceSummary[] = [];
</script>

{#if races.length}
  <section class="py-14 sm:py-20" aria-labelledby="recent-elections">
    <div class="mx-auto max-w-6xl px-4">
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p
            class="text-sm font-semibold uppercase tracking-widest text-blue-600 dark:text-blue-400"
          >
            Published research
          </p>
          <h2
            id="recent-elections"
            class="mt-2 text-3xl font-bold text-content"
          >
            Recently updated elections
          </h2>
        </div>
        <a
          href="/elections/"
          class="font-semibold text-blue-600 hover:underline dark:text-blue-400"
          >Explore all elections</a
        >
      </div>
      <div class="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {#each races as race (race.id)}<RaceCard {race} />{/each}
      </div>
    </div>
  </section>
{/if}
