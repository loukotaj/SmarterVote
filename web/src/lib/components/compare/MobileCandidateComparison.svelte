<script lang="ts">
  import ConfidenceIndicator from "$lib/components/ConfidenceIndicator.svelte";
  import SourceLink from "$lib/components/SourceLink.svelte";
  import type { Candidate, CanonicalIssue, Race } from "$lib/types";
  import { CANONICAL_ISSUES, getIssueDisplayName } from "$lib/types";
  import { candidateSlug } from "$lib/utils/format";
  import { partyAbbr } from "$lib/utils/party";

  export let race: Race;
  export let candidates: Candidate[];
  export let compact = false;
  export let isDraftPreview = false;
  export let showQuality = false;

  let selectedIssue: CanonicalIssue = "Healthcare";
  let expandedStances: Record<string, boolean> = {};

  $: issueKeys = CANONICAL_ISSUES.filter((key) =>
    candidates.some((candidate) => candidate.issues?.[key]?.stance),
  );
  $: if (!issueKeys.includes(selectedIssue))
    selectedIssue = issueKeys[0] ?? "Healthcare";
  $: issueSelectId = `mobile-compare-issue-${race.id}`;

  function stanceKey(candidate: Candidate): string {
    return `${selectedIssue}:${candidate.name}`;
  }

  function stancePreview(stance: string): string {
    const normalized = stance.trim();
    const firstSentence = normalized.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim();
    if (firstSentence) return firstSentence;
    if (normalized.length <= 180) return normalized;

    const shortened = normalized.slice(0, 180);
    const lastSpace = shortened.lastIndexOf(" ");
    return `${shortened.slice(0, lastSpace > 120 ? lastSpace : 180).trim()}…`;
  }

  function toggleStance(candidate: Candidate) {
    const key = stanceKey(candidate);
    expandedStances = { ...expandedStances, [key]: !expandedStances[key] };
  }
</script>

<div
  class="overflow-hidden rounded-2xl border border-stroke bg-surface shadow-sm lg:hidden"
>
  {#if showQuality && race.validation_grade}
    <div
      class="flex items-center gap-3 border-b border-stroke bg-emerald-50/40 px-5 py-3 dark:bg-emerald-950/10"
    >
      <span
        class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-emerald-200 bg-white font-extrabold text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
        >{race.validation_grade.grade}</span
      >
      <p class="text-xs leading-5 text-content-muted">
        <strong class="text-content">Research review:</strong>
        {race.validation_grade.score}/100 after source and consistency checks.
      </p>
    </div>
  {/if}

  <div
    class="flex snap-x snap-mandatory overflow-x-auto border-b border-stroke bg-surface-alt/30"
    aria-label="Candidates in this comparison"
  >
    {#each candidates as candidate}
      <a
        href="/races/{race.id}/{candidateSlug(candidate.name)}{isDraftPreview
          ? '?draft=true'
          : ''}"
        aria-label={candidate.name}
        class="flex w-1/2 min-w-[9.5rem] max-w-[13rem] shrink-0 snap-start flex-col items-center border-r border-stroke px-3 py-4 text-center last:border-0"
      >
        {#if candidate.image_url}
          <img
            src={candidate.image_url}
            alt=""
            class="h-14 w-14 rounded-full border-2 border-white object-cover shadow"
            on:error={(event) => {
              if (event.currentTarget instanceof HTMLImageElement)
                event.currentTarget.style.display = "none";
            }}
          />
        {:else}
          <span
            class="flex h-14 w-14 items-center justify-center rounded-full bg-blue-100 text-sm font-extrabold text-blue-700 dark:bg-blue-900/40 dark:text-blue-300"
          >
            {candidate.name
              .split(" ")
              .map((part) => part[0])
              .slice(0, 2)
              .join("")}
          </span>
        {/if}
        <span class="mt-2 text-sm font-extrabold text-content"
          >{candidate.name}</span
        >
        {#if candidate.party}
          <span class="mt-1 text-[11px] font-semibold text-content-muted"
            >{partyAbbr(candidate.party)}</span
          >
        {/if}
      </a>
    {/each}
  </div>

  <div class="p-4">
    <label
      for={issueSelectId}
      class="text-xs font-extrabold uppercase tracking-wider text-content-subtle"
      >Compare an issue</label
    >
    <select
      id={issueSelectId}
      bind:value={selectedIssue}
      disabled={issueKeys.length === 0}
      class="mt-2 min-h-12 w-full rounded-xl border border-stroke bg-surface px-4 font-bold text-content focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {#if issueKeys.length === 0}
        <option>No researched issues available</option>
      {:else}
        {#each issueKeys as issue}
          <option value={issue}>{getIssueDisplayName(issue)}</option>
        {/each}
      {/if}
    </select>

    <div class="mt-4 space-y-3">
      {#each candidates as candidate}
        {@const stance = candidate.issues?.[selectedIssue]}
        {@const preview = stance ? stancePreview(stance.stance) : ""}
        {@const isExpanded = expandedStances[stanceKey(candidate)] ?? false}
        <article
          aria-label="{candidate.name} position on {getIssueDisplayName(
            selectedIssue,
          )}"
          class="rounded-2xl border border-stroke bg-surface-alt/35 p-4"
        >
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-extrabold text-content">{candidate.name}</h3>
            {#if stance}
              <ConfidenceIndicator confidence={stance.confidence} />
            {/if}
          </div>
          <p class="mt-3 text-sm leading-6 text-content-muted">
            {stance
              ? isExpanded
                ? stance.stance
                : preview
              : "No sourced position available yet."}
          </p>
          {#if stance && preview !== stance.stance.trim()}
            <button
              type="button"
              aria-expanded={isExpanded}
              on:click={() => toggleStance(candidate)}
              class="mt-2 text-sm font-bold text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
            >
              {isExpanded ? "Show less" : "Show more"}
              <span class="sr-only"> for {candidate.name}</span>
            </button>
          {/if}
          {#if stance?.sources?.[0]}
            <div class="mt-3 border-t border-stroke pt-3">
              <SourceLink source={stance.sources[0]} />
            </div>
          {/if}
        </article>
      {/each}
    </div>
    {#if compact}
      <p class="mt-4 text-center text-xs text-content-subtle">
        Choose another issue above, or open the full comparison for every
        research field.
      </p>
    {/if}
  </div>

  {#if race.forecast}
    <div
      class="border-t border-stroke bg-blue-50 px-5 py-4 dark:bg-blue-950/20"
    >
      <div class="flex items-center justify-between gap-3">
        <div>
          <p
            class="text-xs font-extrabold uppercase tracking-wider text-blue-700 dark:text-blue-300"
          >
            Forecast
          </p>
          <p class="mt-1 text-sm capitalize text-content">
            {race.forecast.rating.replaceAll("_", " ")}
          </p>
        </div>
        <a
          href="/races/{race.id}/{isDraftPreview ? '?draft=true' : ''}#forecast"
          class="text-sm font-bold text-blue-600">View forecast →</a
        >
      </div>
    </div>
  {/if}
</div>
