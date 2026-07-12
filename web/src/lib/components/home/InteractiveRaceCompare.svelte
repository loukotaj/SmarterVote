<script lang="ts">
  import CandidateComparison from "$lib/components/compare/CandidateComparison.svelte";
  import ConfidenceIndicator from "$lib/components/ConfidenceIndicator.svelte";
  import SourceLink from "$lib/components/SourceLink.svelte";
  import type { CanonicalIssue, Race } from "$lib/types";
  import { CANONICAL_ISSUES, getIssueDisplayName } from "$lib/types";
  import { candidateSlug } from "$lib/utils/format";

  export let races: Race[] = [];
  let selectedId = races[0]?.id ?? "";
  $: if (races.length && !races.some((race) => race.id === selectedId))
    selectedId = races[0].id;
  $: selectedRace = races.find((race) => race.id === selectedId) ?? races[0];
  $: candidates =
    selectedRace?.candidates
      .filter((candidate) => !candidate.withdrawn)
      .slice(0, 2) ?? [];
  $: mobileIssueKeys = CANONICAL_ISSUES.filter((key) =>
    candidates.some((candidate) => candidate.issues?.[key]?.stance)
  );
  let mobileIssue: CanonicalIssue = "Healthcare";
  $: if (!mobileIssueKeys.includes(mobileIssue))
    mobileIssue = mobileIssueKeys[0] ?? "Healthcare";

  function moveRace(direction: number) {
    const current = races.findIndex((race) => race.id === selectedId);
    const next = (current + direction + races.length) % races.length;
    selectedId = races[next]?.id ?? selectedId;
  }
</script>

{#if selectedRace && candidates.length >= 2}
  <div
    class="flex flex-col overflow-hidden rounded-[1.75rem] border border-blue-200 bg-surface shadow-2xl shadow-blue-950/10 lg:h-[min(760px,calc(100vh-8rem))] lg:min-h-[620px] dark:border-blue-900"
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
          Featured comparison
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
      class="border-b border-stroke px-4 py-3 sm:px-6"
      aria-label="Choose a featured race"
    >
      <div class="flex items-center gap-3">
        <button
          type="button"
          on:click={() => moveRace(-1)}
          class="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-stroke bg-surface text-lg text-content transition hover:border-blue-400 hover:text-blue-600"
          aria-label="Previous featured race">←</button
        >
        <div class="flex min-w-0 flex-1 gap-2 overflow-x-auto py-1">
          {#each races as race, index}
            <button
              type="button"
              on:click={() => (selectedId = race.id)}
              aria-pressed={selectedId === race.id}
              class="whitespace-nowrap rounded-full border px-4 py-2 text-sm font-bold transition {selectedId ===
              race.id
                ? 'border-blue-600 bg-blue-600 text-white shadow-md shadow-blue-600/20'
                : 'border-stroke bg-surface text-content-muted hover:border-blue-400 hover:text-blue-700'}"
            >
              <span class="mr-1 opacity-70"
                >{String(index + 1).padStart(2, "0")}</span
              >
              {race.jurisdiction} · {race.office}
            </button>
          {/each}
        </div>
        <button
          type="button"
          on:click={() => moveRace(1)}
          class="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-stroke bg-surface text-lg text-content transition hover:border-blue-400 hover:text-blue-600"
          aria-label="Next featured race">→</button
        >
      </div>
    </div>

    <div
      class="hidden min-h-0 flex-1 overflow-y-auto p-3 lg:block lg:p-5"
      aria-label="Scrollable featured comparison"
    >
      <CandidateComparison race={selectedRace} {candidates} compact />
      <div
        class="sticky bottom-0 mt-[-2.75rem] flex justify-center bg-gradient-to-t from-surface via-surface/95 to-transparent pb-2 pt-10 pointer-events-none"
      >
        <span
          class="rounded-full border border-stroke bg-surface px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-content-subtle shadow-sm"
          >Scroll for more issues ↓</span
        >
      </div>
    </div>

    <div class="lg:hidden">
      <div class="grid grid-cols-2 border-b border-stroke bg-surface-alt/30">
        {#each candidates as candidate}
          <a
            href="/races/{selectedRace.id}/{candidateSlug(candidate.name)}"
            class="flex min-w-0 flex-col items-center border-r border-stroke px-3 py-4 text-center last:border-0"
          >
            {#if candidate.image_url}
              <img
                src={candidate.image_url}
                alt=""
                class="h-14 w-14 rounded-full border-2 border-white object-cover shadow"
              />
            {/if}
            <span class="mt-2 text-sm font-extrabold text-content"
              >{candidate.name}</span
            >
            <span class="mt-1 text-[11px] font-semibold text-content-muted"
              >{candidate.party}</span
            >
          </a>
        {/each}
      </div>

      {#if selectedRace.forecast}
        <div
          class="border-b border-stroke bg-blue-50 px-5 py-4 dark:bg-blue-950/20"
        >
          <div class="flex items-center justify-between gap-3">
            <div>
              <p
                class="text-xs font-extrabold uppercase tracking-wider text-blue-700 dark:text-blue-300"
              >
                Forecast
              </p>
              <p class="mt-1 text-sm capitalize text-content">
                {selectedRace.forecast.rating.replaceAll("_", " ")}
              </p>
            </div>
            <a href="/forecast/" class="text-sm font-bold text-blue-600"
              >View forecast →</a
            >
          </div>
        </div>
      {/if}

      <div class="p-4">
        <label
          for="mobile-preview-issue"
          class="text-xs font-extrabold uppercase tracking-wider text-content-subtle"
          >Compare an issue</label
        >
        <select
          id="mobile-preview-issue"
          bind:value={mobileIssue}
          class="mt-2 min-h-12 w-full rounded-xl border border-stroke bg-surface px-4 font-bold text-content focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
        >
          {#each mobileIssueKeys as issue}<option value={issue}
              >{getIssueDisplayName(issue)}</option
            >{/each}
        </select>

        <div class="mt-4 space-y-3">
          {#each candidates as candidate}
            {@const stance = candidate.issues?.[mobileIssue]}
            <article
              class="rounded-2xl border border-stroke bg-surface-alt/35 p-4"
            >
              <div class="flex items-center justify-between gap-3">
                <h3 class="font-extrabold text-content">{candidate.name}</h3>
                {#if stance}<ConfidenceIndicator
                    confidence={stance.confidence}
                  />{/if}
              </div>
              <p class="mt-3 text-sm leading-6 text-content-muted">
                {stance?.stance ?? "No sourced position available yet."}
              </p>
              {#if stance?.sources?.[0]}
                <div class="mt-3 border-t border-stroke pt-3">
                  <SourceLink source={stance.sources[0]} />
                </div>
              {/if}
            </article>
          {/each}
        </div>
        <p class="mt-4 text-center text-xs text-content-subtle">
          Choose another issue above, or open the full comparison for every
          research field.
        </p>
      </div>
    </div>
  </div>
{/if}
