<script lang="ts">
  import CandidateComparison from "$lib/components/compare/CandidateComparison.svelte";
  import type { Race } from "$lib/types";

  export let races: Race[] = [];
  let selectedId = races[0]?.id ?? "";
  $: if (races.length && !races.some((race) => race.id === selectedId))
    selectedId = races[0].id;
  $: selectedRace = races.find((race) => race.id === selectedId) ?? races[0];
  $: candidates =
    selectedRace?.candidates
      .filter((candidate) => !candidate.withdrawn)
      .slice(0, 2) ?? [];
</script>

{#if selectedRace && candidates.length >= 2}
  <div
    class="overflow-hidden rounded-[1.75rem] border border-blue-200 bg-surface shadow-2xl shadow-blue-950/10 dark:border-blue-900"
  >
    <div
      class="flex flex-col gap-4 border-b border-stroke bg-surface-alt/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-7"
    >
      <div>
        <div
          class="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-blue-600 dark:text-blue-400"
        >
          <span class="rounded-full bg-blue-600 px-2 py-1 text-white"
            >Grade A</span
          >
          Interactive research preview
        </div>
        <h2
          class="mt-2 text-xl font-extrabold tracking-tight text-content sm:text-2xl"
        >
          {selectedRace.title}
        </h2>
      </div>
      <a
        href="/races/{selectedRace.id}/compare/"
        class="shrink-0 text-sm font-bold text-blue-600 hover:text-blue-800 dark:text-blue-400"
        >Open full comparison →</a
      >
    </div>

    <div
      class="border-b border-stroke px-5 py-3 sm:px-7"
      aria-label="Choose a race to preview"
    >
      <div class="flex gap-2 overflow-x-auto pb-1">
        {#each races as race}
          <button
            type="button"
            on:click={() => (selectedId = race.id)}
            aria-pressed={selectedId === race.id}
            class="whitespace-nowrap rounded-full border px-4 py-2 text-sm font-bold transition {selectedId ===
            race.id
              ? 'border-blue-600 bg-blue-600 text-white shadow-md shadow-blue-600/20'
              : 'border-stroke bg-surface text-content-muted hover:border-blue-400 hover:text-blue-700'}"
          >
            {race.jurisdiction} · {race.office}
          </button>
        {/each}
      </div>
    </div>

    <div class="p-3 sm:p-5">
      <CandidateComparison race={selectedRace} {candidates} compact />
    </div>
  </div>
{/if}
