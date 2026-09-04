<script lang="ts">
  import ReviewScoreInfo from "$lib/components/compare/ReviewScoreInfo.svelte";
  import type { Candidate, Race } from "$lib/types";
  import { candidateSlug } from "$lib/utils/format";
  import { partyAbbr } from "$lib/utils/party";

  export let race: Race;
  export let candidates: Candidate[];

  let failedImages: Record<string, boolean> = {};

  function initials(name: string): string {
    return name
      .split(" ")
      .map((part) => part[0])
      .slice(0, 2)
      .join("");
  }

  function markImageFailed(candidate: Candidate) {
    failedImages = { ...failedImages, [candidate.name]: true };
  }
</script>

<div
  class="overflow-hidden rounded-2xl border border-stroke bg-surface shadow-sm"
>
  {#if race.validation_grade}
    <div
      class="flex items-center gap-3 border-b border-stroke bg-emerald-50/60 px-4 py-3 dark:bg-emerald-950/20 sm:px-5"
    >
      <span
        class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-emerald-200 bg-white text-lg font-extrabold text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
        >{race.validation_grade.grade}</span
      >
      <div class="min-w-0 text-sm text-content-muted">
        <span class="font-bold text-content">Automated Research Score:</span>
        {race.validation_grade.score}/100<ReviewScoreInfo
          panelId={`featured-review-score-info-${race.id}`}
        />
      </div>
    </div>
  {/if}

  <div class="px-4 py-4 sm:px-5">
    <p class="text-xs font-bold uppercase tracking-wider text-content-subtle">
      Candidates
    </p>
    <div
      class="hide-scrollbar mt-3 flex snap-x snap-mandatory gap-2.5 overflow-x-auto pb-1"
      aria-label="All active candidates in this race"
    >
      {#each candidates as candidate}
        <a
          href="/races/{race.id}/{candidateSlug(candidate.name)}/"
          class="group flex min-h-[8.5rem] w-[44%] min-w-36 shrink-0 snap-start flex-col items-center justify-center rounded-xl border border-stroke bg-surface-alt/35 px-2 py-3 text-center no-underline transition hover:border-blue-400 hover:bg-blue-50/50 sm:w-auto sm:min-w-44 sm:flex-1 dark:hover:bg-blue-950/20"
        >
          {#if candidate.image_url && !failedImages[candidate.name]}
            <img
              src={candidate.image_url}
              alt=""
              class="h-12 w-12 rounded-full border-2 border-white object-cover shadow-sm dark:border-slate-800"
              on:error={() => markImageFailed(candidate)}
            />
          {:else}
            <span
              class="flex h-12 w-12 items-center justify-center rounded-full bg-blue-100 text-sm font-extrabold text-blue-700 dark:bg-blue-900/40 dark:text-blue-300"
            >
              {initials(candidate.name)}
            </span>
          {/if}
          <span
            class="mt-2 line-clamp-2 text-sm font-extrabold leading-tight text-content group-hover:text-blue-700 dark:group-hover:text-blue-300"
            >{candidate.name}</span
          >
          {#if candidate.party}
            <span class="mt-1 text-[11px] font-bold text-content-subtle"
              >{partyAbbr(candidate.party)}</span
            >
          {/if}
        </a>
      {/each}
    </div>
    {#if candidates.length > 2}
      <p class="mt-2 text-xs font-semibold text-content-subtle sm:hidden">
        Swipe to see all {candidates.length} candidates.
      </p>
    {/if}
    <p class="mt-3 text-sm leading-6 text-content-muted">
      Compare sourced positions, biographies, and evidence for every candidate
      in this race.
    </p>
  </div>
</div>
