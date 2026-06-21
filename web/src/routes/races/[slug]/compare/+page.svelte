<script lang="ts">
  import { page } from "$app/stores";
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import ConfidenceIndicator from "$lib/components/ConfidenceIndicator.svelte";
  import SourceLink from "$lib/components/SourceLink.svelte";
  import type { Race, Candidate } from "$lib/types";
  import { getRace, getDraftRace } from "$lib/api";
  import { CANONICAL_ISSUES, getIssueDisplayName } from "$lib/types";
  import { candidateSlug } from "$lib/utils/format";
  import { partyAbbr } from "$lib/utils/party";
  import { isExternalUrl } from "$lib/utils/url";

  export let data: { prerenderedRace?: Race };

  let race: Race | null = data.prerenderedRace ?? null;
  let candidates: Candidate[] = [];
  let loading = !race;
  let error: string | null = null;
  let isDraftPreview = false;

  let slug: string;
  $: slug = $page.params.slug as string;

  // Reactively re-run hydrateCandidates whenever the URL searchParams change
  $: if (race && $page) {
    hydrateCandidates();
  }

  onMount(async () => {
    const params = new URLSearchParams(window.location.search);
    isDraftPreview = params.get("draft") === "true";
    const hasPrerenderedRace = !!race && !isDraftPreview;

    try {
      if (isDraftPreview) {
        try {
          race = await getDraftRace(slug);
        } catch {
          race = await getRace(slug, fetch, false);
          isDraftPreview = false;
        }
      } else if (!race) {
        race = await getRace(slug);
      }
    } catch (err) {
      if (hasPrerenderedRace && race) {
        loading = false;
        hydrateCandidates();
        return;
      }
      error = err instanceof Error ? err.message : "Failed to load race data";
    } finally {
      hydrateCandidates();
      loading = false;
    }
  });

  function hydrateCandidates() {
    if (!race) return;
    const candidatesParam = $page.url.searchParams.get("candidates");
    if (candidatesParam) {
      const slugs = candidatesParam.split(",");
      candidates = race.candidates.filter(
        (c) => slugs.includes(candidateSlug(c.name)) && !c.withdrawn
      );
    }
    // If no candidates selected via query params, show first 2 active candidates
    if (candidates.length === 0) {
      candidates = race.candidates.filter((c) => !c.withdrawn).slice(0, 2);
    }
  }

  function toggleSelection(candName: string) {
    if (!race) return;
    const cSlug = candidateSlug(candName);
    const params = new URLSearchParams($page.url.searchParams);
    const candidatesParam = params.get("candidates");
    let currentSlugs = candidatesParam ? candidatesParam.split(",") : [];

    if (currentSlugs.length === 0) {
      currentSlugs = race.candidates
        .filter((c) => !c.withdrawn)
        .slice(0, 2)
        .map((c) => candidateSlug(c.name));
    }

    if (currentSlugs.includes(cSlug)) {
      if (currentSlugs.length > 1) {
        currentSlugs = currentSlugs.filter((s) => s !== cSlug);
      }
    } else {
      currentSlugs.push(cSlug);
    }

    params.set("candidates", currentSlugs.join(","));
    goto(`/races/${slug}/compare?${params.toString()}`, {
      replaceState: true,
      keepFocus: true,
      noScroll: true,
    });
  }
</script>

<svelte:head>
  <title>Compare Candidates | {race?.title || "Smarter.vote"}</title>
  <meta
    name="description"
    content="Compare candidates side-by-side on key election issues for {race?.title ||
      'this election'}."
  />
  <link rel="canonical" href="https://smarter.vote/races/{slug}/compare/" />
  <meta
    property="og:url"
    content="https://smarter.vote/races/{slug}/compare/"
  />
  <meta
    property="og:title"
    content="Compare Candidates | {race?.title || 'Smarter.vote'}"
  />
  <meta
    property="og:description"
    content="Compare candidates side-by-side on key election issues for {race?.title ||
      'this election'}."
  />
  <meta property="og:image" content="https://smarter.vote/og-image.png" />
  <meta property="twitter:card" content="summary_large_image" />
  <meta
    property="twitter:url"
    content="https://smarter.vote/races/{slug}/compare/"
  />
  <meta
    property="twitter:title"
    content="Compare Candidates | {race?.title || 'Smarter.vote'}"
  />
  <meta
    property="twitter:description"
    content="Compare candidates side-by-side on key election issues for {race?.title ||
      'this election'}."
  />
  <meta property="twitter:image" content="https://smarter.vote/og-image.png" />
</svelte:head>

<div class="container mx-auto px-4 py-6 sm:py-8 max-w-7xl">
  <!-- Navigation header -->
  <header
    class="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
  >
    <div>
      <nav class="mb-1 text-xs text-content-subtle uppercase tracking-wide">
        <a href="/" class="hover:text-content">Home</a> &middot;
        <a
          href="/races/{slug}{isDraftPreview ? '?draft=true' : ''}"
          class="hover:text-content">Race Detail</a
        >
        &middot;
        <span class="text-content-muted">Compare</span>
      </nav>
      <h1
        class="text-2xl sm:text-3xl font-extrabold text-content tracking-tight"
      >
        Compare Candidates
      </h1>
      {#if race}
        <p class="text-sm text-content-muted mt-1">
          {race.office}{race.district ? ` (${race.district})` : ""} &bull; {race.jurisdiction}
        </p>
      {/if}
    </div>
    <a
      href="/races/{slug}{isDraftPreview ? '?draft=true' : ''}"
      class="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold border border-stroke rounded-lg hover:bg-surface-alt transition-colors no-underline text-content"
    >
      <svg
        class="w-4 h-4"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M15 19l-7-7 7-7"
        />
      </svg>
      Back to Race Overview
    </a>
  </header>

  {#if loading}
    <!-- Skeleton Loading State -->
    <div class="space-y-6">
      <div
        class="h-16 bg-surface border border-stroke rounded-xl animate-pulse"
      />
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div
          class="h-96 bg-surface border border-stroke rounded-xl animate-pulse md:col-span-3"
        />
      </div>
    </div>
  {:else if error}
    <div
      class="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg p-6 text-center"
    >
      <h2 class="text-xl font-bold text-red-800 dark:text-red-200 mb-2">
        Error
      </h2>
      <p class="text-red-600 dark:text-red-400">{error}</p>
      <a
        href="/races/{slug}"
        class="mt-4 inline-block text-blue-600 dark:text-blue-400 font-semibold underline"
      >
        Return to Race Overview
      </a>
    </div>
  {:else if race && candidates.length === 0}
    <div
      class="bg-surface border border-stroke rounded-xl p-8 text-center text-content-subtle"
    >
      <p class="text-lg font-semibold text-content">No Candidates Selected</p>
      <p class="mt-2 text-sm">
        Please select candidates from the race detail page to compare them.
      </p>
      <a
        href="/races/{slug}"
        class="mt-4 inline-flex btn-primary no-underline text-sm font-semibold"
      >
        Go Select Candidates
      </a>
    </div>
  {:else if race}
    <!-- Candidate Selector Filter Bar -->
    <div
      class="mb-6 p-4 bg-surface border border-stroke rounded-2xl shadow-sm flex flex-col gap-3"
    >
      <span
        class="text-xs font-extrabold uppercase text-content-subtle tracking-wider"
        >Choose candidates to compare:</span
      >
      <div class="flex flex-wrap gap-2.5">
        {#each race.candidates.filter((c) => !c.withdrawn) as c}
          {@const isChecked = candidates.some(
            (selected) => selected.name === c.name
          )}
          <label
            class="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border border-stroke bg-surface-alt/40 hover:bg-surface-alt transition-colors cursor-pointer text-xs sm:text-sm font-semibold text-content select-none"
          >
            <input
              type="checkbox"
              checked={isChecked}
              on:change={() => toggleSelection(c.name)}
              class="w-4 h-4 cursor-pointer text-blue-600 border-stroke rounded focus:ring-blue-500 bg-surface"
            />
            {c.name}
            {#if c.party}
              <span class="text-[10px] text-content-subtle font-bold"
                >({partyAbbr(c.party)})</span
              >
            {/if}
          </label>
        {/each}
      </div>
    </div>

    <!-- Main comparison dashboard -->
    <div
      class="overflow-x-auto border border-stroke rounded-2xl shadow-sm bg-surface"
    >
      <div class="min-w-[768px]">
        <!-- Sticky Candidate Names/Avatars Row -->
        <div
          class="sticky top-[57px] md:top-[65px] z-30 w-full min-w-full bg-surface/95 backdrop-blur-md border-b border-stroke py-4 shadow-sm"
        >
          <div
            class="grid items-center"
            style="grid-template-columns: 220px repeat({candidates.length}, 1fr)"
          >
            <div
              class="sticky left-0 z-40 bg-surface/95 px-6 font-bold text-xs uppercase tracking-wider text-content-subtle border-r border-stroke"
            >
              Compare Directory
            </div>
            {#each candidates as candidate}
              <div
                class="px-6 flex items-center gap-3 border-r border-stroke last:border-none"
              >
                {#if candidate.image_url}
                  <img
                    src={candidate.image_url}
                    alt=""
                    class="w-12 h-12 rounded-full object-cover border-2 border-stroke flex-shrink-0"
                    on:error={(e) => {
                      if (e.currentTarget instanceof HTMLImageElement)
                        e.currentTarget.style.display = "none";
                    }}
                  />
                {:else}
                  <div
                    class="w-12 h-12 rounded-full bg-blue-100 dark:bg-blue-900/40 flex items-center justify-center flex-shrink-0 text-sm font-bold text-blue-700 dark:text-blue-300"
                  >
                    {candidate.name
                      .split(" ")
                      .map((n) => n[0])
                      .slice(0, 2)
                      .join("")}
                  </div>
                {/if}
                <div class="min-w-0">
                  <a
                    href="/races/{race.id}/{candidateSlug(
                      candidate.name
                    )}{isDraftPreview ? '?draft=true' : ''}"
                    class="font-extrabold text-sm text-content hover:text-blue-600 block truncate"
                  >
                    {candidate.name}
                  </a>
                  <div class="flex items-center gap-1.5 mt-0.5">
                    {#if candidate.party}
                      <span
                        class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-surface-alt border border-stroke text-content-muted capitalize leading-none"
                      >
                        {partyAbbr(candidate.party)}
                      </span>
                    {/if}
                    {#if candidate.incumbent}
                      <span
                        class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300 leading-none"
                      >
                        Incumbent
                      </span>
                    {/if}
                  </div>
                </div>
              </div>
            {/each}
          </div>
        </div>

        <!-- Comparative Grid Matrix -->
        <div class="divide-y divide-stroke">
          <!-- Biography / Summary -->
          <div
            class="grid"
            style="grid-template-columns: 220px repeat({candidates.length}, 1fr)"
          >
            <div
              class="sticky left-0 z-10 bg-surface-alt p-5 font-bold text-sm text-content border-r border-stroke flex items-center"
            >
              Biography & Summary
            </div>
            {#each candidates as candidate}
              <div
                class="p-6 text-sm text-content-muted leading-relaxed border-r border-stroke last:border-none"
              >
                {candidate.summary}
                {#if isExternalUrl(candidate.website)}
                  <div class="mt-3">
                    <a
                      href={candidate.website.trim()}
                      target="_blank"
                      rel="noopener noreferrer"
                      class="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 font-semibold hover:underline"
                    >
                      Visit Campaign Website
                      <svg
                        class="w-3 h-3"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          stroke-width="2"
                          d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                        />
                      </svg>
                    </a>
                  </div>
                {/if}
              </div>
            {/each}
          </div>

          <!-- Stances section header -->
          <div
            class="sticky left-0 z-10 bg-surface-alt/40 px-6 py-2.5 font-bold text-xs uppercase tracking-wider text-content-subtle w-full min-w-full"
          >
            Positions on Key Issues
          </div>

          <!-- Issues -->
          {#each CANONICAL_ISSUES as issueKey}
            <div
              class="grid"
              style="grid-template-columns: 220px repeat({candidates.length}, 1fr)"
            >
              <!-- Issue Title Column -->
              <div
                class="sticky left-0 z-10 bg-surface-alt p-5 font-bold text-sm text-content border-r border-stroke flex flex-col justify-center"
              >
                {getIssueDisplayName(issueKey)}
              </div>

              <!-- Stances Columns -->
              {#each candidates as candidate}
                {@const stance = candidate.issues?.[issueKey]}
                <div
                  class="p-6 border-r border-stroke last:border-none flex flex-col gap-3"
                >
                  {#if stance}
                    <p
                      class="text-sm text-content-muted leading-relaxed whitespace-normal"
                    >
                      {stance.stance}
                    </p>
                    <div class="flex items-center gap-2 pt-1">
                      <span
                        class="text-[10px] text-content-subtle font-medium uppercase tracking-wide"
                        >Confidence</span
                      >
                      <ConfidenceIndicator confidence={stance.confidence} />
                    </div>
                    {#if stance.sources && stance.sources.length > 0}
                      <div
                        class="pt-2 border-t border-stroke/40 flex flex-wrap gap-1"
                      >
                        {#each stance.sources.slice(0, 3) as source}
                          <SourceLink {source} />
                        {/each}
                      </div>
                    {/if}
                  {:else}
                    <span class="text-xs text-content-faint italic select-none"
                      >No stance researched yet.</span
                    >
                  {/if}
                </div>
              {/each}
            </div>
          {/each}

          <!-- Background / Timelines Header -->
          <div
            class="sticky left-0 z-10 bg-surface-alt/40 px-6 py-2.5 font-bold text-xs uppercase tracking-wider text-content-subtle w-full min-w-full"
          >
            Background & Credentials
          </div>

          <!-- Career timelines -->
          <div
            class="grid"
            style="grid-template-columns: 220px repeat({candidates.length}, 1fr)"
          >
            <div
              class="sticky left-0 z-10 bg-surface-alt p-5 font-bold text-sm text-content border-r border-stroke flex items-center"
            >
              Career Timeline
            </div>
            {#each candidates as candidate}
              <div
                class="p-6 border-r border-stroke last:border-none text-sm text-content-muted"
              >
                {#if candidate.career_history && candidate.career_history.length > 0}
                  <div class="space-y-4">
                    {#each candidate.career_history as entry}
                      <div class="border-l-2 border-blue-500/50 pl-3 py-0.5">
                        <div
                          class="flex items-baseline justify-between gap-2 flex-wrap"
                        >
                          <span class="font-semibold text-content text-xs"
                            >{entry.title}</span
                          >
                          {#if entry.start_year}
                            <span class="text-[10px] text-content-subtle">
                              {entry.start_year}{entry.end_year
                                ? ` – ${entry.end_year}`
                                : " – Present"}
                            </span>
                          {/if}
                        </div>
                        {#if entry.organization}
                          <span class="text-xs text-content-subtle block"
                            >{entry.organization}</span
                          >
                        {/if}
                      </div>
                    {/each}
                  </div>
                {:else}
                  <span class="text-xs text-content-faint italic select-none"
                    >No career records.</span
                  >
                {/if}
              </div>
            {/each}
          </div>

          <!-- Education -->
          <div
            class="grid"
            style="grid-template-columns: 220px repeat({candidates.length}, 1fr)"
          >
            <div
              class="sticky left-0 z-10 bg-surface-alt p-5 font-bold text-sm text-content border-r border-stroke flex items-center"
            >
              Education
            </div>
            {#each candidates as candidate}
              <div
                class="p-6 border-r border-stroke last:border-none text-sm text-content-muted"
              >
                {#if candidate.education && candidate.education.length > 0}
                  <div class="space-y-3">
                    {#each candidate.education as edu}
                      <div>
                        <span class="font-semibold text-content text-xs block"
                          >{edu.institution}</span
                        >
                        {#if edu.degree || edu.field}
                          <span class="text-[11px] text-content-subtle">
                            {[edu.degree, edu.field]
                              .filter(Boolean)
                              .join(" in ")}
                            {#if edu.year} ({edu.year}){/if}
                          </span>
                        {/if}
                      </div>
                    {/each}
                  </div>
                {:else}
                  <span class="text-xs text-content-faint italic select-none"
                    >No education records.</span
                  >
                {/if}
              </div>
            {/each}
          </div>

          <!-- Top Donors -->
          <div
            class="grid"
            style="grid-template-columns: 220px repeat({candidates.length}, 1fr)"
          >
            <div
              class="sticky left-0 z-10 bg-surface-alt p-5 font-bold text-sm text-content border-r border-stroke flex items-center"
            >
              Financial Donors
            </div>
            {#each candidates as candidate}
              <div
                class="p-6 border-r border-stroke last:border-none text-sm text-content-muted"
              >
                {#if candidate.donor_summary}
                  <p class="text-xs leading-relaxed mb-3">
                    {candidate.donor_summary}
                  </p>
                  {#if isExternalUrl(candidate.donor_source_url)}
                    <a
                      href={candidate.donor_source_url.trim()}
                      target="_blank"
                      rel="noopener noreferrer"
                      class="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 font-semibold hover:underline"
                    >
                      Open FEC Donor Details
                      <svg
                        class="w-3 h-3"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          stroke-width="2"
                          d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                        />
                      </svg>
                    </a>
                  {/if}
                {:else}
                  <span class="text-xs text-content-faint italic select-none"
                    >No donor records available.</span
                  >
                {/if}
              </div>
            {/each}
          </div>

          <!-- Voting Record -->
          <div
            class="grid"
            style="grid-template-columns: 220px repeat({candidates.length}, 1fr)"
          >
            <div
              class="sticky left-0 z-10 bg-surface-alt p-5 font-bold text-sm text-content border-r border-stroke flex items-center"
            >
              Voting Record
            </div>
            {#each candidates as candidate}
              <div
                class="p-6 border-r border-stroke last:border-none text-sm text-content-muted"
              >
                {#if candidate.voting_summary}
                  <p class="text-xs leading-relaxed mb-3">
                    {candidate.voting_summary}
                  </p>
                  {#if isExternalUrl(candidate.voting_source_url)}
                    <a
                      href={candidate.voting_source_url.trim()}
                      target="_blank"
                      rel="noopener noreferrer"
                      class="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 font-semibold hover:underline"
                    >
                      Open Detailed Voting Source
                      <svg
                        class="w-3 h-3"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          stroke-width="2"
                          d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                        />
                      </svg>
                    </a>
                  {/if}
                {:else}
                  <span class="text-xs text-content-faint italic select-none"
                    >No voting summary available.</span
                  >
                {/if}
              </div>
            {/each}
          </div>
        </div>
      </div>
    </div>
  {/if}
</div>
