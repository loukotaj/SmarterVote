<script lang="ts">
  import { page } from "$app/stores";
  import { onMount } from "svelte";
  import CandidateCard from "$lib/components/CandidateCard.svelte";
  import ReviewPanel from "$lib/components/ReviewPanel.svelte";
  import ValidationGradeBadge from "$lib/components/ValidationGradeBadge.svelte";
  import Card from "$lib/components/Card.svelte";
  import type { Race } from "$lib/types";
  import { getRace, getDraftRace } from "$lib/api";
  import { formatModelName, candidateSlug } from "$lib/utils/format";
  import { partySlug, partyAbbr } from "$lib/utils/party";

  let race: Race | null = null;
  let loading = true;
  let error: string | null = null;
  let usingFallbackData = false;
  let isDraftPreview = false;

  let slug: string;
  $: slug = $page.params.slug as string;

  onMount(async () => {
    const params = new URLSearchParams(window.location.search);
    isDraftPreview = params.get("draft") === "true";

    try {
      if (isDraftPreview) {
        race = await getDraftRace(slug);
      } else {
        race = await getRace(slug);
      }
      usingFallbackData = false;
    } catch (err) {
      // Try to use fallback data
      try {
        race = await getRace(slug, fetch, true);
        usingFallbackData = true;
        error = null;
      } catch (fallbackErr) {
        error = err instanceof Error ? err.message : "Failed to load race data";
        usingFallbackData = false;
      }
    } finally {
      loading = false;
    }
  });

  $: activeCandidates = race?.candidates?.filter(c => !c.withdrawn) ?? [];
  $: withdrawnCandidates = race?.candidates?.filter(c => c.withdrawn) ?? [];
  $: candidateCount = activeCandidates.length;
  $: incumbents = activeCandidates.filter(c => c.incumbent);
  $: parties = [...new Set(activeCandidates.map(c => c.party).filter(Boolean))];
  let withdrawnExpanded = false;
  $: polls = race?.polling ?? [];
  $: latestPoll = polls.length > 0 ? polls[0] : null;
  $: latestMatchup = latestPoll?.matchups?.[0] ?? null;
  $: discoveryOnly = activeCandidates.length > 0 &&
    activeCandidates.every(c => !c.issues || Object.keys(c.issues).length === 0 ||
      Object.values(c.issues).every(i => !i?.stance));

  function partyClassForName(name: string): string {
    const candidate = race?.candidates?.find(c => c.name === name);
    return partySlug(candidate?.party);
  }
</script>

<svelte:head>
  <title>{race?.title || "Loading..."} | Smarter.vote</title>
  <meta
    name="description"
    content="Compare candidates for {race?.title ||
      'this election'} on key issues using analysis from traceable public sources."
  />
</svelte:head>

<div class="container mx-auto px-4 py-6 sm:py-8 max-w-7xl">
  {#if loading}
    <div class="loading-wrapper">
      <div class="spinner" />
      <span class="loading-text">Loading race data...</span>
    </div>
  {:else if error}
    <div class="error-box">
      <h2 class="error-title">Error Loading Race</h2>
      <p class="text-red-600">{error}</p>
      <button class="error-button" on:click={() => window.location.reload()}>
        Try Again
      </button>
    </div>
  {:else if race}
    {#if isDraftPreview}
      <div class="mb-4 rounded-lg border-2 border-amber-400 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-600 px-4 py-3 text-sm text-amber-800 dark:text-amber-200 flex items-center gap-2">
        <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" /></svg>
        <span><strong>Draft Preview</strong> — This data has not been published. Only admins can see this page.</span>
      </div>
    {/if}
    {#if discoveryOnly}
      <div class="mb-4 rounded-lg border-2 border-blue-300 bg-blue-50 dark:bg-blue-900/20 dark:border-blue-600 px-4 py-3 text-sm text-blue-800 dark:text-blue-200 flex items-start gap-3">
        <svg class="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        <div>
          <p class="font-semibold">Limited Data — Discovery Only</p>
          <p class="mt-1 text-blue-700 dark:text-blue-300">This race has basic candidate information but detailed issue positions have not been researched yet. Want detailed data on this race? <a href="https://github.com/loukotaj/SmarterVote/issues/new/choose" target="_blank" rel="noopener noreferrer" class="underline font-medium hover:text-blue-900 dark:hover:text-blue-100">Request a research run</a> or <a href="https://github.com/sponsors/loukotaj" target="_blank" rel="noopener noreferrer" class="underline font-medium hover:text-blue-900 dark:hover:text-blue-100">sponsor to help fund it</a>!</p>
        </div>
      </div>
    {/if}
    <!-- Race Header -->
    <Card tag="header" class="header-card">
      <div class="header-top">
        <h1 class="header-title">{race.title}</h1>
        {#if race.validation_grade}
          <ValidationGradeBadge grade={race.validation_grade} />
        {/if}
      </div>
      <div class="header-meta">
        <div class="info-row">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          <span>Election: {new Date(race.election_date).toLocaleDateString()}</span>
        </div>
        <div class="info-row">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <span>{race.office}{race.district ? ` (${race.district})` : ''} &bull; {race.jurisdiction}</span>
        </div>
        <div class="info-row">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>Updated: {new Date(race.updated_utc).toLocaleDateString()}</span>
        </div>
      </div>
    </Card>

    <!-- Race Overview -->
    <Card class="overview-card">
      <div class="overview-layout">
        <!-- Left: description + candidate chips -->
        <div class="overview-main">
          {#if race.description}
            <p class="overview-description">{race.description}</p>
          {/if}
          <div class="overview-candidates">
            {#each activeCandidates as candidate}
              <a href="/races/{race.id}/{candidateSlug(candidate.name)}{isDraftPreview ? '?draft=true' : ''}" class="overview-candidate-chip">
                {#if candidate.image_url}
                  <img src={candidate.image_url} alt="" class="chip-avatar" on:error={(e) => { if (e.currentTarget instanceof HTMLImageElement) e.currentTarget.style.display = 'none'; }} />
                {/if}
                <span class="chip-name">{candidate.name}</span>
                {#if candidate.party}
                  <span class="chip-party chip-party-{partyClassForName(candidate.name)}">{partyAbbr(candidate.party)}</span>
                {/if}
                {#if candidate.incumbent}
                  <span class="chip-incumbent">Incumbent</span>
                {/if}
              </a>
            {/each}
          </div>
        </div>

        <!-- Right: poll snapshot widget -->
        {#if latestPoll && latestMatchup}
          <a href="#polls" class="poll-snapshot">
            <div class="poll-snapshot-header">
              <svg class="w-4 h-4 text-blue-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              <span class="poll-snapshot-title">Latest Poll</span>
            </div>
            <p class="poll-snapshot-meta">{latestPoll.pollster}{latestPoll.date ? ` · ${new Date(latestPoll.date).toLocaleDateString('en-US', {month:'short', day:'numeric'})}` : ''}</p>
            <div class="poll-snapshot-bars">
              {#each latestMatchup.candidates as name, i}
                <div class="poll-snap-row">
                  <span class="poll-snap-name">{name.split(' ').pop()}</span>
                  <div class="poll-snap-bar-wrap">
                    <div class="poll-snap-bar {partyClassForName(name)}" style="width:{Math.min(latestMatchup.percentages[i] ?? 0, 100)}%"></div>
                  </div>
                  <span class="poll-snap-pct">{latestMatchup.percentages[i]}%</span>
                </div>
              {/each}
            </div>
            {#if polls.length > 1}
              <span class="poll-snapshot-more">{polls.length} polls total — view all ↓</span>
            {:else}
              <span class="poll-snapshot-more">View detailed results ↓</span>
            {/if}
          </a>
        {/if}
      </div>
    </Card>

    <!-- Fallback Data Notice -->
    {#if usingFallbackData}
      <div class="fallback-notice">
        <div class="fallback-content">
          <svg class="w-5 h-5 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
          <div>
            <p class="fallback-title">Using Sample Data</p>
            <p class="fallback-text">Live data is currently unavailable. The information shown below is sample data for demonstration purposes.</p>
          </div>
        </div>
      </div>
    {/if}

    <!-- Candidates Section -->
    <section>
      <h2 class="candidates-title">Candidates</h2>
      <div class="candidate-grid">
        {#each activeCandidates as candidate}
          <CandidateCard {candidate} raceId={race.id} draft={isDraftPreview} />
        {/each}
      </div>
    </section>

    <!-- Withdrawn Candidates -->
    {#if withdrawnCandidates.length > 0}
      <section class="mt-4">
        <button
          class="flex items-center gap-2 text-sm text-content-muted hover:text-content transition-colors"
          on:click={() => (withdrawnExpanded = !withdrawnExpanded)}
          aria-expanded={withdrawnExpanded}
        >
          <svg class="w-4 h-4 transition-transform {withdrawnExpanded ? 'rotate-90' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
          Withdrawn / Not Running ({withdrawnCandidates.length})
        </button>
        {#if withdrawnExpanded}
          <div class="candidate-grid mt-3 opacity-60">
            {#each withdrawnCandidates as candidate}
              <CandidateCard {candidate} raceId={race.id} draft={isDraftPreview} />
            {/each}
          </div>
        {/if}
      </section>
    {/if}

    <!-- Detailed Polls Section -->
    {#if polls.length > 0}
      <section id="polls" class="polls-section">
        <h2 class="section-heading">Polling</h2>
        <div class="polls-grid">
          {#each polls as poll}
            <div class="poll-card">
              <div class="poll-card-header">
                <div>
                  <span class="poll-card-pollster">{poll.pollster}</span>
                  {#if poll.date}
                    <span class="poll-card-date">{new Date(poll.date).toLocaleDateString('en-US', {year:'numeric', month:'short', day:'numeric'})}</span>
                  {/if}
                </div>
                {#if poll.sample_size}
                  <span class="poll-card-sample">n={poll.sample_size.toLocaleString()}</span>
                {/if}
              </div>

              {#each (poll.matchups ?? []) as matchup, mi}
                {#if mi > 0}<div class="poll-matchup-divider"></div>{/if}
                <div class="poll-matchup">
                  {#each matchup.candidates as name, i}
                    {@const pc = partyClassForName(name)}
                    <div class="poll-bar-row">
                      <span class="poll-bar-name">{name}</span>
                      <div class="poll-bar-track">
                        <div class="poll-bar-fill {pc}" style="width:{Math.min(matchup.percentages[i] ?? 0, 100)}%">
                          <span class="poll-bar-label">{matchup.percentages[i]}%</span>
                        </div>
                      </div>
                    </div>
                  {/each}
                </div>
              {/each}

              {#if poll.source_url}
                <a href={poll.source_url} target="_blank" rel="noopener noreferrer" class="poll-card-source">
                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                  Source
                </a>
              {/if}
            </div>
          {/each}
        </div>
      </section>
    {/if}

    <!-- Data Note -->
    <div class="data-note">
      <p class="data-note-title">{usingFallbackData ? "Sample Data Information" : "Data Analysis Information"}</p>
      <p class="data-note-text">
        {#if usingFallbackData}
          This is sample data for demonstration purposes. The actual race data is currently unavailable.
        {:else}
          Data compiled from public sources and analyzed using AI. Last updated {new Date(race.updated_utc).toLocaleDateString()}. Visit candidate websites for the most current information.
        {/if}
      </p>
    </div>

    <!-- AI Review Status (bottom) -->
    <ReviewPanel reviews={race.reviews ?? []} />

    <!-- Models used to generate this race -->
    {#if race.generator && race.generator.length > 0}
      <div class="model-label">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
        <span>Models:</span>
        {#each race.generator as model}
          <span class="model-tag">{formatModelName(model)}</span>
        {/each}
      </div>
    {/if}

    <!-- Back to Top -->
    <div class="back-to-top">
      <button class="back-to-top-link" on:click={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18" />
        </svg>
        Back to Top
      </button>
    </div>
  {/if}
</div>

<style lang="postcss">
  .loading-wrapper {
    @apply flex items-center justify-center py-20;
  }

  .spinner {
    @apply animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600;
  }

  .loading-text {
    @apply ml-3 text-lg text-content-muted;
  }

  .error-box {
    @apply bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg p-6 text-center;
  }

  .error-title {
    @apply text-2xl font-bold text-red-800 dark:text-red-200 mb-2;
  }

  .error-button {
    @apply mt-4 bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700 transition-colors;
  }

  :global(.header-card) {
    @apply p-4 sm:p-6 mb-6 sm:mb-8 shadow-sm;
  }

  .header-title {
    @apply text-2xl sm:text-3xl lg:text-4xl font-bold text-content capitalize;
  }

  .header-top {
    @apply flex flex-wrap items-start sm:items-center justify-between gap-3 mb-4;
  }

  .header-meta {
    @apply flex flex-col sm:flex-row sm:flex-wrap items-start sm:items-center gap-3 sm:gap-6 text-content-muted;
  }

  .info-row {
    @apply flex items-center gap-2;
  }

  .model-label {
    @apply mt-2 mb-4 flex flex-wrap items-center gap-2 text-sm text-content-subtle;
  }

  .model-tag {
    @apply bg-surface-alt px-2 py-1 rounded text-xs font-mono;
  }

  .candidates-title {
    @apply text-xl sm:text-2xl font-semibold text-content mb-4 sm:mb-6;
  }

  /* Race Overview */
  :global(.overview-card) {
    @apply p-4 sm:p-6 mb-6 sm:mb-8 shadow-sm;
  }

  .overview-layout {
    @apply flex flex-col lg:flex-row gap-6;
  }

  .overview-main {
    @apply flex-1 min-w-0;
  }

  .overview-description {
    @apply text-content-muted text-sm sm:text-base leading-relaxed mb-4;
  }

  .overview-candidates {
    @apply flex flex-wrap gap-2;
  }

  .overview-candidate-chip {
    @apply flex items-center gap-1.5 px-3 py-1.5 bg-surface border border-stroke rounded-full
           hover:border-blue-300 hover:bg-blue-50 dark:hover:bg-blue-950/30 transition-colors duration-200 text-sm no-underline text-content-muted;
  }

  .chip-avatar {
    @apply w-5 h-5 rounded-full object-cover;
  }

  .chip-name {
    @apply font-medium text-content text-sm;
  }

  .chip-party {
    @apply text-xs font-semibold;
  }
  .chip-party-dem { @apply text-blue-600; }
  .chip-party-rep { @apply text-red-600; }

  .chip-incumbent {
    @apply bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 text-xs px-1.5 py-0.5 rounded-full;
  }

  /* Poll Snapshot Widget */
  .poll-snapshot {
    @apply flex flex-col gap-2 p-4 bg-page border border-stroke rounded-xl
           hover:border-blue-300 hover:bg-blue-50 transition-colors no-underline
           lg:w-64 lg:shrink-0 cursor-pointer;
  }

  .poll-snapshot-header {
    @apply flex items-center gap-1.5;
  }

  .poll-snapshot-title {
    @apply text-sm font-semibold text-content;
  }

  .poll-snapshot-meta {
    @apply text-xs text-content-subtle;
  }

  .poll-snapshot-bars {
    @apply space-y-1.5 my-1;
  }

  .poll-snap-row {
    @apply flex items-center gap-2;
  }

  .poll-snap-name {
    @apply text-xs font-medium text-content-muted w-16 shrink-0 truncate;
  }

  .poll-snap-bar-wrap {
    @apply flex-1 bg-surface-alt rounded-full h-2 overflow-hidden;
  }

  .poll-snap-bar {
    @apply h-full rounded-full bg-content-faint;
  }
  .poll-snap-bar.dem { @apply bg-blue-500; }
  .poll-snap-bar.rep { @apply bg-red-500; }

  .poll-snap-pct {
    @apply text-xs font-bold text-content-muted w-8 text-right shrink-0;
  }

  .poll-snapshot-more {
    @apply text-xs text-blue-600 font-medium mt-1;
  }

  /* Candidates */
  .candidates-title {
    @apply text-xl sm:text-2xl font-semibold text-content mb-4 sm:mb-6;
  }

  .candidate-grid {
    @apply grid gap-6 sm:gap-8 justify-items-stretch;
  }

  /* Detailed Polls Section */
  .polls-section {
    @apply mt-10 mb-8;
  }

  .section-heading {
    @apply text-xl sm:text-2xl font-semibold text-content mb-4 sm:mb-6;
  }

  .polls-grid {
    @apply grid gap-4 sm:grid-cols-2 lg:grid-cols-3;
  }

  .poll-card {
    @apply bg-surface border border-stroke rounded-xl p-4 shadow-sm flex flex-col gap-3;
  }

  .poll-card-header {
    @apply flex items-start justify-between gap-2;
  }

  .poll-card-pollster {
    @apply text-sm font-semibold text-content block;
  }

  .poll-card-date {
    @apply text-xs text-content-subtle block mt-0.5;
  }

  .poll-card-sample {
    @apply text-xs text-content-faint shrink-0;
  }

  .poll-matchup-divider {
    @apply border-t border-dashed border-stroke;
  }

  .poll-matchup {
    @apply space-y-2;
  }

  .poll-bar-row {
    @apply flex items-center gap-2;
  }

  .poll-bar-name {
    @apply text-xs font-medium text-content-muted w-28 shrink-0 truncate;
  }

  .poll-bar-track {
    @apply flex-1 bg-surface-alt rounded-full h-6 overflow-hidden;
  }

  .poll-bar-fill {
    @apply h-full rounded-full bg-content-faint flex items-center justify-end pr-2 min-w-[2rem] transition-all duration-300;
  }
  .poll-bar-fill.dem { @apply bg-blue-500; }
  .poll-bar-fill.rep { @apply bg-red-500; }

  .poll-bar-label {
    @apply text-xs font-bold text-white;
  }

  .poll-card-source {
    @apply inline-flex items-center gap-1 text-xs text-blue-500 hover:text-blue-700 mt-auto;
  }

  /* Misc */
  .data-note {
    @apply mt-8 sm:mt-10 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-lg p-4 sm:p-6 text-center;
  }

  .data-note-title {
    @apply text-blue-800 dark:text-blue-200 font-medium mb-2 text-sm sm:text-base;
  }

  .data-note-text {
    @apply text-blue-700 dark:text-blue-300 text-xs sm:text-sm;
  }

  .fallback-notice {
    @apply bg-yellow-50 dark:bg-yellow-950/30 border border-yellow-200 dark:border-yellow-800 rounded-lg p-3 sm:p-4 mb-6 sm:mb-8;
  }

  .fallback-content {
    @apply flex items-start gap-2 sm:gap-3;
  }

  .fallback-title {
    @apply font-medium text-yellow-800 dark:text-yellow-200 text-sm sm:text-base;
  }

  .fallback-text {
    @apply text-yellow-700 dark:text-yellow-300 text-xs sm:text-sm mt-1;
  }

  .back-to-top {
    @apply mt-8 text-center;
  }

  .back-to-top-link {
    @apply inline-flex items-center gap-2 text-content-muted hover:text-blue-600 font-medium transition-colors duration-200 border-none bg-transparent cursor-pointer;
  }
</style>
