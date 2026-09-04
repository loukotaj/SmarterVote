<script lang="ts">
  import ConfidenceIndicator from "$lib/components/ConfidenceIndicator.svelte";
  import MobileCandidateComparison from "$lib/components/compare/MobileCandidateComparison.svelte";
  import ReviewScoreInfo from "$lib/components/compare/ReviewScoreInfo.svelte";
  import SourceLink from "$lib/components/SourceLink.svelte";
  import type { Candidate, Race } from "$lib/types";
  import { CANONICAL_ISSUES, getIssueDisplayName } from "$lib/types";
  import { candidateSlug } from "$lib/utils/format";
  import { partyAbbr } from "$lib/utils/party";
  import { stancePreview } from "$lib/utils/stance";
  import { isExternalUrl } from "$lib/utils/url";

  export let race: Race;
  export let candidates: Candidate[];
  export let compact = false;
  export let isDraftPreview = false;
  export let showQuality = false;
  export let onToggle: ((candidateName: string) => void) | undefined =
    undefined;

  let expandedSources: Record<string, boolean> = {};
  let expandedStances: Record<string, boolean> = {};
  let failedImages: Record<string, boolean> = {};

  function stanceKey(issue: string, candidate: Candidate): string {
    return `${issue}:${candidate.name}:stance`;
  }

  function toggleStance(issue: string, candidate: Candidate) {
    const key = stanceKey(issue, candidate);
    expandedStances = { ...expandedStances, [key]: !expandedStances[key] };
  }

  function sourcesKey(issue: string, candidate: Candidate): string {
    return `${issue}:${candidate.name}`;
  }

  function toggleSources(issue: string, candidate: Candidate) {
    const key = sourcesKey(issue, candidate);
    expandedSources = { ...expandedSources, [key]: !expandedSources[key] };
  }

  function markImageFailed(candidate: Candidate) {
    failedImages = { ...failedImages, [candidate.name]: true };
  }

  function initials(name: string): string {
    return name
      .split(" ")
      .map((part) => part[0])
      .slice(0, 2)
      .join("");
  }

  const backgroundRows: Array<{
    label: string;
    summary: "donor_summary" | "voting_summary";
    url: "donor_source_url" | "voting_source_url";
    link: string;
  }> = [
    {
      label: "Financial Donors",
      summary: "donor_summary",
      url: "donor_source_url",
      link: "Open FEC Donor Details",
    },
    {
      label: "Voting Record",
      summary: "voting_summary",
      url: "voting_source_url",
      link: "Open Detailed Voting Source",
    },
  ];

  $: issueKeys = compact
    ? CANONICAL_ISSUES.filter((key) =>
        candidates.some((candidate) => {
          const stance = candidate.issues?.[key];
          return stance && stance.sources && stance.sources.length > 0;
        }),
      ).slice(0, 1)
    : CANONICAL_ISSUES;

  function forecastProbability(candidate: Candidate): number | undefined {
    const forecast = race.forecast;
    if (!forecast) return undefined;
    if (forecast.predicted_winner_name === candidate.name)
      return forecast.win_probability;
    const party = candidate.party?.toLowerCase() ?? "";
    const match = Object.entries(forecast.party_probabilities ?? {}).find(
      ([key]) =>
        party.includes(key.toLowerCase()) ||
        key.toLowerCase().includes(party) ||
        key.toLowerCase() === party.charAt(0),
    );
    return match?.[1];
  }
</script>

{#if onToggle}
  <div
    class="mb-6 flex flex-col gap-3 rounded-2xl border border-stroke bg-surface p-4 shadow-sm"
  >
    <h2
      class="text-xs font-extrabold uppercase tracking-wider text-content-subtle"
    >
      Choose candidates to compare:
    </h2>
    <div class="flex flex-wrap gap-2.5">
      {#each race.candidates.filter((candidate) => !candidate.withdrawn) as candidate}
        {@const checked = candidates.some(
          (selected) => selected.name === candidate.name,
        )}
        <label
          class="inline-flex min-h-11 cursor-pointer select-none items-center gap-2 rounded-xl border border-stroke bg-surface-alt/40 px-3 py-1.5 text-xs font-semibold text-content transition-colors hover:bg-surface-alt sm:text-sm"
        >
          <input
            type="checkbox"
            {checked}
            on:change={() => onToggle?.(candidate.name)}
            class="h-4 w-4 cursor-pointer rounded border-stroke bg-surface text-blue-600 focus:ring-blue-500"
          />
          {candidate.name}
          {#if candidate.party}<span
              class="text-[10px] font-bold text-content-subtle"
              >({partyAbbr(candidate.party)})</span
            >{/if}
        </label>
      {/each}
    </div>
  </div>
{/if}

<MobileCandidateComparison
  {race}
  {candidates}
  {compact}
  {isDraftPreview}
  {showQuality}
/>

<div
  data-desktop-candidate-comparison
  class="hidden isolate overflow-hidden rounded-2xl border border-stroke bg-surface shadow-sm lg:block"
>
  {#if showQuality && race.validation_grade}
    <div
      class="flex items-start gap-3 border-b border-stroke bg-emerald-50 px-5 py-3.5 dark:bg-emerald-950/30"
    >
      <span
        class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-emerald-200 bg-white text-lg font-extrabold text-emerald-800 shadow-sm dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
        >{race.validation_grade.grade}</span
      >
      <div class="min-w-0 text-sm leading-6 text-content-muted">
        <span
          class="mr-1.5 text-[10px] font-bold uppercase tracking-wider text-content-subtle"
          >Automated Research Score</span
        >
        <strong class="text-content">{race.validation_grade.score}/100</strong
        ><ReviewScoreInfo panelId={`desktop-review-score-info-${race.id}`} />
      </div>
    </div>
  {/if}

  <div class="overflow-x-auto custom-scrollbar">
    <div
      style="min-width: {(compact ? 170 : 220) + candidates.length * 250}px"
      role="table"
      aria-label="Candidate comparison"
      aria-colcount={candidates.length + 1}
    >
      <div
        class:sticky={!compact}
        class:top-[var(--site-header-height)]={!compact}
        class="z-30 w-full border-b border-stroke bg-surface py-4 shadow-sm"
      >
        <div
          class="grid items-center"
          role="row"
          style="grid-template-columns: {compact
            ? '170px'
            : '220px'} repeat({candidates.length}, 1fr)"
        >
          <div
            role="columnheader"
            class="sticky left-0 z-40 flex self-stretch items-center border-r border-stroke bg-surface px-5 text-xs font-bold uppercase tracking-wider text-content-subtle"
          >
            {compact ? "Compare" : "Candidate comparison"}
          </div>
          {#each candidates as candidate}
            <div
              role="columnheader"
              class="flex items-center gap-3 border-r border-stroke px-5 last:border-none"
            >
              {#if candidate.image_url && !failedImages[candidate.name]}
                <img
                  src={candidate.image_url}
                  alt=""
                  class="h-12 w-12 flex-shrink-0 rounded-full border-2 border-stroke object-cover"
                  on:error={() => markImageFailed(candidate)}
                />
              {:else}
                <div
                  class="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-700 dark:bg-blue-900/40 dark:text-blue-300"
                >
                  {initials(candidate.name)}
                </div>
              {/if}
              <div class="min-w-0">
                <a
                  href="/races/{race.id}/{candidateSlug(
                    candidate.name,
                  )}/{isDraftPreview ? '?draft=true' : ''}"
                  class="block truncate text-sm font-extrabold text-content hover:text-blue-600"
                  >{candidate.name}</a
                >
                <div class="mt-0.5 flex items-center gap-1.5">
                  {#if candidate.party}<span
                      class="rounded border border-stroke bg-surface-alt px-1.5 py-0.5 text-[10px] font-bold leading-none text-content-muted"
                      >{partyAbbr(candidate.party)}</span
                    >{/if}
                  {#if candidate.incumbent}<span
                      class="rounded border border-green-200 bg-green-50 px-1.5 py-0.5 text-[10px] font-bold leading-none text-green-700 dark:border-green-800 dark:bg-green-950/20 dark:text-green-300"
                      >Incumbent</span
                    >{/if}
                </div>
              </div>
            </div>
          {/each}
        </div>
      </div>

      <div class="divide-y divide-stroke">
        <div
          class="grid"
          role="row"
          style="grid-template-columns: {compact
            ? '170px'
            : '220px'} repeat({candidates.length}, 1fr)"
        >
          <div
            role="rowheader"
            class="sticky left-0 z-10 flex items-center border-r border-stroke bg-surface-alt p-5 text-sm font-bold text-content"
          >
            Biography & Summary
          </div>
          {#each candidates as candidate}
            <div
              role="cell"
              class="border-r border-stroke p-6 text-sm leading-relaxed text-content-muted last:border-none"
            >
              {candidate.summary}
              {#if !compact && isExternalUrl(candidate.website)}<div
                  class="mt-3"
                >
                  <a
                    href={candidate.website.trim()}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-xs font-semibold text-blue-600 hover:underline dark:text-blue-400"
                    >Visit campaign website ↗</a
                  >
                </div>{/if}
            </div>
          {/each}
        </div>

        <div
          class="grid"
          role="row"
          style="grid-template-columns: {compact
            ? '170px'
            : '220px'} repeat({candidates.length}, 1fr)"
        >
          <div
            role="columnheader"
            class="col-span-full sticky left-0 z-10 w-full bg-surface-alt/40 px-6 py-2.5 text-xs font-bold uppercase tracking-wider text-content-subtle"
            style="grid-column: 1 / -1"
          >
            Positions on Key Issues
          </div>
        </div>
        {#each issueKeys as issueKey}
          <div
            class="grid"
            role="row"
            style="grid-template-columns: {compact
              ? '170px'
              : '220px'} repeat({candidates.length}, 1fr)"
          >
            <div
              role="rowheader"
              class="sticky left-0 z-10 flex flex-col justify-center border-r border-stroke bg-surface-alt p-5 text-sm font-bold text-content"
            >
              {getIssueDisplayName(issueKey)}
            </div>
            {#each candidates as candidate}
              {@const stance = candidate.issues?.[issueKey]}
              {@const preview = stance
                ? stancePreview(stance.stance, 320, 220)
                : ""}
              {@const isStanceExpanded =
                expandedStances[stanceKey(issueKey, candidate)] ?? false}
              <div
                role="cell"
                class="flex flex-col gap-3 border-r border-stroke p-6 last:border-none"
              >
                {#if stance}
                  <div>
                    <p
                      class="whitespace-normal text-sm leading-relaxed text-content-muted"
                    >
                      {isStanceExpanded ? stance.stance : preview}
                    </p>
                    {#if preview !== stance.stance.trim()}
                      <button
                        type="button"
                        aria-expanded={isStanceExpanded}
                        on:click={() => toggleStance(issueKey, candidate)}
                        class="inline-flex min-h-11 items-start pt-1 text-sm font-bold leading-5 text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                      >
                        {isStanceExpanded ? "Show less" : "Show more"}
                        <span class="sr-only"> for {candidate.name}</span>
                      </button>
                    {/if}
                  </div>
                  <div class="flex items-center gap-2 pt-1">
                    <span
                      class="text-[10px] font-medium uppercase tracking-wide text-content-subtle"
                      >Confidence</span
                    ><ConfidenceIndicator confidence={stance.confidence} />
                  </div>
                  {#if stance.sources?.length}
                    {@const areSourcesExpanded =
                      expandedSources[sourcesKey(issueKey, candidate)] ?? false}
                    <div class="border-t border-stroke/40 pt-2">
                      <div class="flex flex-col items-start gap-2">
                        {#each areSourcesExpanded ? stance.sources : stance.sources.slice(0, 1) as source}
                          <SourceLink {source} />
                        {/each}
                      </div>
                      {#if stance.sources.length > 1}
                        <button
                          type="button"
                          aria-expanded={areSourcesExpanded}
                          on:click={() => toggleSources(issueKey, candidate)}
                          class="mt-1 inline-flex min-h-11 items-center text-xs font-bold text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                        >
                          {areSourcesExpanded
                            ? "Show fewer sources"
                            : `Show ${stance.sources.length - 1} more ${stance.sources.length === 2 ? "source" : "sources"}`}
                          <span class="sr-only"> for {candidate.name}</span>
                        </button>
                      {/if}
                    </div>
                  {/if}
                {:else}<span
                    class="select-none text-xs italic text-content-faint"
                    >No stance researched yet.</span
                  >{/if}
              </div>
            {/each}
          </div>
        {/each}

        {#if !compact}
          <div
            class="grid"
            role="row"
            style="grid-template-columns: 220px repeat({candidates.length}, 1fr)"
          >
            <div
              role="columnheader"
              class="col-span-full sticky left-0 z-10 w-full bg-surface-alt/40 px-6 py-2.5 text-xs font-bold uppercase tracking-wider text-content-subtle"
              style="grid-column: 1 / -1"
            >
              Background & Credentials
            </div>
          </div>
          <div
            class="grid"
            role="row"
            style="grid-template-columns: 220px repeat({candidates.length}, 1fr)"
          >
            <div
              role="rowheader"
              class="sticky left-0 z-10 flex items-center border-r border-stroke bg-surface-alt p-5 text-sm font-bold text-content"
            >
              Career Timeline
            </div>
            {#each candidates as candidate}<div
                role="cell"
                class="border-r border-stroke p-6 text-sm text-content-muted last:border-none"
              >
                {#if candidate.career_history?.length}<div class="space-y-4">
                    {#each candidate.career_history as entry}<div
                        class="border-l-2 border-blue-500/50 py-0.5 pl-3"
                      >
                        <div
                          class="flex flex-wrap items-baseline justify-between gap-2"
                        >
                          <span class="text-xs font-semibold text-content"
                            >{entry.title}</span
                          >{#if entry.start_year}<span
                              class="text-[10px] text-content-subtle"
                              >{entry.start_year}{entry.end_year
                                ? ` – ${entry.end_year}`
                                : " – Present"}</span
                            >{/if}
                        </div>
                        {#if entry.organization}<span
                            class="block text-xs text-content-subtle"
                            >{entry.organization}</span
                          >{/if}
                      </div>{/each}
                  </div>{:else}<span class="text-xs italic text-content-faint"
                    >No career records.</span
                  >{/if}
              </div>{/each}
          </div>
          <div
            class="grid"
            role="row"
            style="grid-template-columns: 220px repeat({candidates.length}, 1fr)"
          >
            <div
              role="rowheader"
              class="sticky left-0 z-10 flex items-center border-r border-stroke bg-surface-alt p-5 text-sm font-bold text-content"
            >
              Education
            </div>
            {#each candidates as candidate}<div
                role="cell"
                class="border-r border-stroke p-6 text-sm text-content-muted last:border-none"
              >
                {#if candidate.education?.length}<div class="space-y-3">
                    {#each candidate.education as edu}<div>
                        <span class="block text-xs font-semibold text-content"
                          >{edu.institution}</span
                        >{#if edu.degree || edu.field}<span
                            class="text-[11px] text-content-subtle"
                            >{[edu.degree, edu.field]
                              .filter(Boolean)
                              .join(" in ")}{#if edu.year}
                              ({edu.year}){/if}</span
                          >{/if}
                      </div>{/each}
                  </div>{:else}<span class="text-xs italic text-content-faint"
                    >No education records.</span
                  >{/if}
              </div>{/each}
          </div>
          {#each backgroundRows as row}
            <div
              class="grid"
              role="row"
              style="grid-template-columns: 220px repeat({candidates.length}, 1fr)"
            >
              <div
                role="rowheader"
                class="sticky left-0 z-10 flex items-center border-r border-stroke bg-surface-alt p-5 text-sm font-bold text-content"
              >
                {row.label}
              </div>
              {#each candidates as candidate}{@const summary =
                  candidate[row.summary]}{@const sourceUrl = candidate[row.url]}
                <div
                  role="cell"
                  class="border-r border-stroke p-6 text-sm text-content-muted last:border-none"
                >
                  {#if summary}<p class="mb-3 text-xs leading-relaxed">
                      {summary}
                    </p>
                    {#if sourceUrl && isExternalUrl(sourceUrl)}<a
                        href={sourceUrl.trim()}
                        target="_blank"
                        rel="noopener noreferrer"
                        class="text-xs font-semibold text-blue-600 hover:underline dark:text-blue-400"
                        >{row.link} ↗</a
                      >{/if}{:else}<span
                      class="text-xs italic text-content-faint"
                      >No records available.</span
                    >{/if}
                </div>{/each}
            </div>
          {/each}
        {/if}

        {#if race.forecast}
          <div
            class="grid"
            role="row"
            style="grid-template-columns: {compact
              ? '170px'
              : '220px'} repeat({candidates.length}, 1fr)"
          >
            <div
              role="rowheader"
              class="sticky left-0 z-10 border-r border-stroke bg-blue-50 p-5 text-sm font-bold text-content dark:bg-blue-950/20"
            >
              Forecast
              <span
                class="mt-1 block text-[10px] font-semibold uppercase tracking-wider text-content-subtle"
                >Model estimate</span
              >
            </div>
            {#each candidates as candidate}
              {@const probability = forecastProbability(candidate)}
              <div
                role="cell"
                class="border-r border-stroke bg-blue-50/40 p-5 last:border-none dark:bg-blue-950/10"
              >
                {#if probability !== undefined}
                  <div class="text-2xl font-extrabold text-content">
                    {Math.round(probability * 100)}%
                  </div>
                  <p class="mt-1 text-xs text-content-muted">
                    estimated win probability
                  </p>
                {:else}
                  <p class="text-sm font-semibold capitalize text-content">
                    {race.forecast.rating.replaceAll("_", " ")}
                  </p>
                  <p class="mt-1 text-xs text-content-muted">
                    race-level rating
                  </p>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </div>
  </div>
</div>
