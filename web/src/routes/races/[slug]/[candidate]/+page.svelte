<script lang="ts">
  import { page } from "$app/stores";
  import { onMount } from "svelte";
  import Card from "$lib/components/Card.svelte";
  import IssueTable from "$lib/components/IssueTable.svelte";
  import DonorTable from "$lib/components/DonorTable.svelte";
  import VotingRecordTable from "$lib/components/VotingRecordTable.svelte";
  import type { Race, Candidate } from "$lib/types";
  import { getRace, getDraftRace } from "$lib/api";
  import { candidateSlug, formatModelName } from "$lib/utils/format";

  let race: Race | null = null;
  let candidate: Candidate | null = null;
  let otherCandidates: Candidate[] = [];
  let loading = true;
  let error: string | null = null;
  let othersExpanded = false;
  let isDraftPreview = false;

  let slug: string;
  let candidateParam: string;
  $: slug = $page.params.slug as string;
  $: candidateParam = $page.params.candidate as string;

  onMount(async () => {
    const params = new URLSearchParams(window.location.search);
    isDraftPreview = params.get("draft") === "true";

    try {
      if (isDraftPreview) {
        race = await getDraftRace(slug);
      } else {
        race = await getRace(slug);
      }
    } catch (err) {
      try {
        race = await getRace(slug, fetch, true);
      } catch {
        error = err instanceof Error ? err.message : "Failed to load race data";
      }
    }

    if (race) {
      candidate =
        race.candidates?.find(
          (c) => candidateSlug(c.name) === candidateParam
        ) ?? null;
      otherCandidates =
        race.candidates?.filter(
          (c) => candidateSlug(c.name) !== candidateParam
        ) ?? [];
      if (!candidate) {
        error = "Candidate not found";
      }
    }
    loading = false;
  });

  $: hasCareer =
    candidate && candidate.career_history && candidate.career_history.length > 0;
  $: hasEducation =
    candidate && candidate.education && candidate.education.length > 0;
  $: hasVoting = !!(candidate && candidate.voting_summary);
  $: hasDonors = !!(candidate && candidate.donor_summary);
  $: candidateDiscoveryOnly = candidate != null &&
    (!candidate.issues || Object.keys(candidate.issues).length === 0 ||
      Object.values(candidate.issues).every(i => !i?.stance));
</script>

<svelte:head>
  <title
    >{candidate?.name ?? "Candidate"} — {race?.title ?? "Loading..."} | Smarter.vote</title
  >
  <meta
    name="description"
    content="Detailed profile for {candidate?.name ?? 'candidate'} in {race?.title ?? 'this election'}."
  />
</svelte:head>

<div class="container mx-auto px-4 py-6 sm:py-8 max-w-4xl">
  {#if loading}
    <div class="flex items-center justify-center py-20">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600" />
      <span class="ml-3 text-lg text-content-muted">Loading candidate...</span>
    </div>
  {:else if error}
    <div class="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg p-6 text-center">
      <h2 class="text-2xl font-bold text-red-800 dark:text-red-200 mb-2">{error}</h2>
      <a href="/races/{slug}" class="mt-4 inline-block text-blue-600 hover:text-blue-400 font-medium">
        &larr; Back to race overview
      </a>
    </div>
  {:else if candidate && race}
    {#if isDraftPreview}
      <div class="mb-4 rounded-lg border-2 border-amber-400 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-600 px-4 py-3 text-sm text-amber-800 dark:text-amber-200 flex items-center gap-2">
        <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" /></svg>
        <span><strong>Draft Preview</strong> — This data has not been published. Only admins can see this page.</span>
      </div>
    {/if}
    {#if candidateDiscoveryOnly}
      <div class="mb-4 rounded-lg border-2 border-blue-300 bg-blue-50 dark:bg-blue-900/20 dark:border-blue-600 px-4 py-3 text-sm text-blue-800 dark:text-blue-200 flex items-start gap-3">
        <svg class="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        <div>
          <p class="font-semibold">Limited Data — Discovery Only</p>
          <p class="mt-1 text-blue-700 dark:text-blue-300">This candidate has basic biographical information but detailed issue positions have not been researched yet. Want detailed data? <a href="mailto:info@smarter.vote?subject=Research%20request:%20{encodeURIComponent(race?.title ?? slug)}" class="underline font-medium hover:text-blue-900 dark:hover:text-blue-100">Request a research run</a> or <a href="https://smarter.vote/sponsor" class="underline font-medium hover:text-blue-900 dark:hover:text-blue-100">sponsor to help fund it</a>!</p>
        </div>
      </div>
    {/if}
    <!-- Navigation Bar -->
    <nav class="nav-bar">
      <a href="/races/{slug}" class="back-link">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
        Back to {race.title}
      </a>
      <div class="model-label">
        {#each (race.generator ?? []) as model}
          <span class="model-tag">{formatModelName(model)}</span>
        {/each}
      </div>
    </nav>

    <!-- Other Candidates (Collapsible) -->
    {#if otherCandidates.length > 0}
      <div class="other-candidates-bar">
        <button
          class="toggle-others"
          on:click={() => (othersExpanded = !othersExpanded)}
          aria-expanded={othersExpanded}
        >
          <span>Other Candidates ({otherCandidates.length})</span>
          <svg
            class="w-4 h-4 transition-transform duration-200"
            class:rotate-180={othersExpanded}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        {#if othersExpanded}
          <div class="others-list">
            {#each otherCandidates as other}
              <a
                href="/races/{race.id}/{candidateSlug(other.name)}"
                class="other-chip"
              >
                {#if other.image_url}
                  <img
                    src={other.image_url}
                    alt=""
                    class="other-avatar"
                    on:error={(e) => {
                      if (e.currentTarget instanceof HTMLImageElement) e.currentTarget.style.display = "none";
                    }}
                  />
                {/if}
                <div class="other-info">
                  <span class="other-name">{other.name}</span>
                  {#if other.party}
                    <span class="other-party">{other.party}</span>
                  {/if}
                </div>
              </a>
            {/each}
          </div>
        {/if}
      </div>
    {/if}

    <!-- Candidate Header -->
    <Card class="candidate-header-card">
      <div class="candidate-top">
        {#if candidate.image_url}
          <img
            src={candidate.image_url}
            alt={candidate.name}
            class="candidate-photo"
            on:error={(e) => {
              if (e.currentTarget instanceof HTMLImageElement) e.currentTarget.style.display = "none";
            }}
          />
        {:else}
          <div class="candidate-photo-placeholder">
            <svg class="w-12 h-12 text-gray-400" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
            </svg>
          </div>
        {/if}
        <div class="candidate-headline">
          <h1 class="candidate-detail-name">{candidate.name}</h1>
          <div class="flex flex-wrap items-center gap-2 mt-1">
            {#if candidate.party}
              <span class="badge party-badge">{candidate.party}</span>
            {/if}
            {#if candidate.incumbent}
              <span class="badge incumbent-badge">Incumbent</span>
            {/if}
          </div>
        </div>
      </div>

      <p class="candidate-summary">{candidate.summary}</p>

      <!-- Quick links -->
      <div class="quick-links">
        {#if candidate.website}
          <a href={candidate.website} target="_blank" rel="noopener noreferrer" class="quick-link">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9" />
            </svg>
            Campaign Website
          </a>
        {/if}
        {#each Object.entries(candidate.social_media ?? {}) as [platform, url]}
          <a href={url} target="_blank" rel="noopener noreferrer" class="quick-link">
            <span class="capitalize">{platform}</span>
          </a>
        {/each}
      </div>
    </Card>

    <!-- Issues Section -->
    <section class="detail-section">
      <h2 class="section-heading">Positions on Key Issues</h2>
      <Card class="section-card">
        <IssueTable issues={candidate.issues} raceId={race.id} candidateName={candidate.name} />
      </Card>
    </section>

    <!-- Background Section -->
    {#if hasCareer || hasEducation}
      <section class="detail-section">
        <h2 class="section-heading">Background</h2>
        <Card class="section-card">
          {#if hasCareer}
            <div class="mb-6">
              <h3 class="subsection-title">Career History</h3>
              <div class="timeline">
                {#each candidate.career_history as entry}
                  <div class="timeline-entry">
                    <div class="timeline-header">
                      <span class="timeline-title">{entry.title}</span>
                      {#if entry.start_year}
                        <span class="timeline-years">
                          {entry.start_year}{entry.end_year ? ` – ${entry.end_year}` : " – Present"}
                        </span>
                      {/if}
                    </div>
                    {#if entry.organization}
                      <span class="timeline-org">{entry.organization}</span>
                    {/if}
                    {#if entry.description}
                      <p class="timeline-desc">{entry.description}</p>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {/if}
          {#if hasEducation}
            <div>
              <h3 class="subsection-title">Education</h3>
              <div class="space-y-2">
                {#each candidate.education as edu}
                  <div class="edu-entry">
                    <span class="edu-institution">{edu.institution}</span>
                    {#if edu.degree || edu.field}
                      <span class="edu-degree">
                        {[edu.degree, edu.field].filter(Boolean).join(" in ")}
                        {#if edu.year}({edu.year}){/if}
                      </span>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {/if}
        </Card>
      </section>
    {/if}

    <!-- Top Donors Section -->
    {#if hasDonors}
      <section class="detail-section">
        <h2 class="section-heading">Top Donors</h2>
        <Card class="section-card">
          <DonorTable
            donorSummary={candidate.donor_summary || ''}
            donorSourceUrl={candidate.donor_source_url || ''}
            raceId={race.id}
            candidateName={candidate.name}
          />
        </Card>
      </section>
    {/if}

    <!-- Voting Record Section -->
    {#if hasVoting}
      <section class="detail-section">
        <h2 class="section-heading">Voting Record</h2>
        <Card class="section-card">
          <VotingRecordTable
            votingSummary={candidate.voting_summary || ''}
            votingSourceUrl={candidate.voting_source_url || ''}
            raceId={race.id}
            candidateName={candidate.name}
          />
        </Card>
      </section>
    {/if}

    <!-- Data Note -->
    <div class="data-note">
      <p class="data-note-title">Data Analysis Information</p>
      <p class="data-note-text">
        Data compiled from public sources and analyzed using AI. Last updated
        {new Date(race.updated_utc).toLocaleDateString()}. Visit candidate
        websites for the most current information.
      </p>
    </div>
  {/if}
</div>

<style lang="postcss">
  .nav-bar {
    @apply flex items-center justify-between mb-6 flex-wrap gap-3;
  }

  .back-link {
    @apply inline-flex items-center gap-1.5 text-blue-600 hover:text-blue-800
           font-medium text-sm no-underline transition-colors duration-200;
  }

  .model-label {
    @apply flex items-center gap-1.5 text-xs text-content-subtle;
  }

  .model-tag {
    @apply bg-surface-alt text-content-subtle px-2 py-0.5 rounded font-mono text-xs;
  }

  /* Other candidates collapsible */
  .other-candidates-bar {
    @apply mb-6 bg-surface-alt border border-stroke rounded-lg overflow-hidden;
  }

  .toggle-others {
    @apply w-full flex items-center justify-between px-4 py-3 text-sm font-medium
           text-content hover:bg-stroke/30 transition-colors duration-200;
  }

  .others-list {
    @apply px-4 pb-4 flex flex-wrap gap-3;
  }

  .other-chip {
    @apply flex items-center gap-2.5 px-3 py-2 bg-surface border border-stroke
           rounded-lg hover:border-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950 transition-colors
           duration-200 no-underline text-content;
  }

  .other-avatar {
    @apply w-8 h-8 rounded-full object-cover;
  }

  .other-info {
    @apply flex flex-col;
  }

  .other-name {
    @apply text-sm font-medium text-content;
  }

  .other-party {
    @apply text-xs text-content-subtle;
  }

  /* Candidate header */
  :global(.candidate-header-card) {
    @apply p-5 sm:p-6 mb-6 shadow-sm;
  }

  .candidate-top {
    @apply flex items-start gap-5 mb-4;
  }

  .candidate-photo {
    @apply w-24 h-24 sm:w-28 sm:h-28 rounded-xl object-cover border-2 border-stroke flex-shrink-0;
  }

  .candidate-photo-placeholder {
    @apply w-24 h-24 sm:w-28 sm:h-28 rounded-xl bg-surface-alt border-2 border-stroke
           flex items-center justify-center flex-shrink-0;
  }

  .candidate-detail-name {
    @apply text-2xl sm:text-3xl font-bold text-content;
  }

  .badge {
    @apply px-2.5 py-1 rounded-full text-xs sm:text-sm font-medium;
  }

  .party-badge {
    @apply bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200;
  }

  .incumbent-badge {
    @apply bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200;
  }

  .candidate-summary {
    @apply text-content-muted leading-relaxed text-sm sm:text-base mb-4;
  }

  .quick-links {
    @apply flex flex-wrap gap-2;
  }

  .quick-link {
    @apply inline-flex items-center gap-1.5 px-3 py-1.5 bg-surface-alt border
           border-stroke rounded-md text-sm text-content hover:bg-blue-50 dark:hover:bg-blue-950
           hover:border-blue-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors
           duration-200 no-underline;
  }

  /* Sections */
  .detail-section {
    @apply mb-6;
  }

  .section-heading {
    @apply text-lg sm:text-xl font-semibold text-content mb-3;
  }

  :global(.section-card) {
    @apply p-4 sm:p-6 shadow-sm;
  }

  .subsection-title {
    @apply text-base font-semibold text-content mb-3;
  }

  /* Timeline */
  .timeline {
    @apply space-y-3;
  }

  .timeline-entry {
    @apply border-l-2 border-blue-300 dark:border-blue-700 pl-4 py-1;
  }

  .timeline-header {
    @apply flex flex-wrap items-baseline gap-2;
  }

  .timeline-title {
    @apply font-medium text-content text-sm;
  }

  .timeline-years {
    @apply text-xs text-content-subtle;
  }

  .timeline-org {
    @apply text-sm text-content-muted block;
  }

  .timeline-desc {
    @apply text-xs text-content-subtle mt-1;
  }

  /* Education */
  .edu-entry {
    @apply flex flex-col;
  }

  .edu-institution {
    @apply font-medium text-content text-sm;
  }

  .edu-degree {
    @apply text-xs text-content-muted;
  }

  /* Data note */
  .data-note {
    @apply mt-8 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg p-4 sm:p-6 text-center;
  }

  .data-note-title {
    @apply text-blue-800 dark:text-blue-200 font-medium mb-2 text-sm sm:text-base;
  }

  .data-note-text {
    @apply text-blue-700 dark:text-blue-300 text-xs sm:text-sm;
  }
</style>
