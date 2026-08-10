<script lang="ts">
  import type { RaceSummary } from "$lib/types";
  import { raceDisplayTitle } from "$lib/utils/raceTitle";
  export let races: RaceSummary[] = [];
</script>

{#if races.length}
  <section
    class="border-t border-stroke py-20 sm:py-28"
    aria-labelledby="featured-elections"
  >
    <div class="mx-auto max-w-6xl px-4 sm:px-6">
      <header
        class="flex items-end justify-between gap-6 border-b border-stroke pb-6"
      >
        <div>
          <p
            class="text-xs font-bold uppercase tracking-[0.24em] text-blue-600 dark:text-blue-400"
          >
            The research desk
          </p>
          <h2
            id="featured-elections"
            class="mt-3 text-3xl font-bold tracking-tight text-content sm:text-5xl"
          >
            Featured races
          </h2>
        </div>
        <a
          href="/elections/"
          class="hidden text-sm font-semibold text-blue-600 transition hover:text-blue-800 sm:block dark:text-blue-400"
          >View the full index →</a
        >
      </header>

      <div class="grid lg:grid-cols-[1.4fr_.8fr]">
        <a
          href="/races/{races[0].id}/"
          class="group border-b border-stroke py-8 lg:border-b-0 lg:border-r lg:pr-10"
        >
          <div
            class="flex items-center gap-3 text-xs font-semibold uppercase tracking-widest text-content-subtle"
          >
            <span class="rounded-full bg-blue-600 px-3 py-1 text-white"
              >Featured</span
            >
            <span>Competitive race</span>
          </div>
          <h3
            class="mt-8 max-w-2xl text-3xl font-bold leading-tight tracking-tight text-content transition group-hover:text-blue-600 sm:text-5xl dark:group-hover:text-blue-400"
          >
            {races[0].title ?? races[0].office ?? "Election research"}
          </h3>
          <p class="mt-4 text-lg text-content-muted">
            {races[0].jurisdiction ?? "United States"}
          </p>
          <div class="mt-10 flex flex-wrap gap-3">
            {#each races[0].candidates.slice(0, 4) as candidate}
              <span
                class="rounded-full border border-stroke px-4 py-2 text-sm font-medium text-content"
                >{candidate.name}</span
              >
            {/each}
          </div>
          <p class="mt-10 font-semibold text-blue-600 dark:text-blue-400">
            Open the election guide <span
              class="inline-block transition group-hover:translate-x-1">→</span
            >
          </p>
        </a>

        <div class="lg:pl-10">
          {#each races.slice(1, 5) as race}
            <a
              href="/races/{race.id}/"
              class="group block border-b border-stroke py-6 last:border-0"
            >
              <p
                class="text-xs font-semibold uppercase tracking-widest text-content-subtle"
              >
                {race.jurisdiction ?? "National"} · Competitive race
              </p>
              <h3
                class="mt-2 text-xl font-bold leading-snug text-content transition group-hover:text-blue-600 dark:group-hover:text-blue-400"
              >
                {raceDisplayTitle(race)}
              </h3>
              <p class="mt-2 text-sm text-content-muted">
                {race.candidates.length} candidates researched
              </p>
            </a>
          {/each}
        </div>
      </div>
      <a
        href="/elections/"
        class="mt-8 inline-block text-sm font-semibold text-blue-600 sm:hidden dark:text-blue-400"
        >View the full index →</a
      >
    </div>
  </section>
{/if}
