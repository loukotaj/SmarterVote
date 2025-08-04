<script lang="ts">
  import { page } from "$app/stores";
  import { onMount } from "svelte";
  import CandidateCard from "$lib/components/CandidateCard.svelte";
  import Card from "$lib/components/Card.svelte";
  import type { Race } from "$lib/types";
  import { getRace } from "$lib/api";

  let race: Race | null = null;
  let loading = true;
  let error: string | null = null;
  let usingFallbackData = false;

  let slug: string;
  $: slug = $page.params.slug as string;

  onMount(async () => {
    try {
      race = await getRace(slug);
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
</script>

<svelte:head>
  <title>{race?.title || "Loading..."} | Smarter.vote</title>
  <meta
    name="description"
    content="Compare candidates for {race?.title ||
      'this election'} on key issues with AI-powered analysis."
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
    <!-- Race Header -->
    <Card tag="header" class="header-card">
      <h1 class="header-title">{race.title}</h1>
      <div class="header-meta">
        <div class="info-row">
          <svg
            class="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
          <span
            >Election: {new Date(race.election_date).toLocaleDateString()}</span
          >
        </div>
        <div class="info-row">
          <svg
            class="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
            />
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
            />
          </svg>
          <span>{race.office} • {race.jurisdiction}</span>
        </div>
        <div class="info-row">
          <svg
            class="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>Updated: {new Date(race.updated_utc).toLocaleDateString()}</span
          >
        </div>
      </div>
      <div class="model-label">
        <span>Analysis by:</span>
        {#each race.generator as model}
          <span class="model-tag">{model}</span>
        {/each}
      </div>
    </Card>

    <!-- Fallback Data Notice -->
    {#if usingFallbackData}
      <div class="fallback-notice">
        <div class="fallback-content">
          <svg
            class="w-5 h-5 text-yellow-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z"
            />
          </svg>
          <div>
            <p class="fallback-title">Using Sample Data</p>
            <p class="fallback-text">
              Live data is currently unavailable. The information shown below is sample data for demonstration purposes.
            </p>
          </div>
        </div>
      </div>
    {/if}

    <!-- Candidates Section -->
    <section>
      <h2 class="candidates-title">Candidates</h2>
      
      <!-- Candidate Navigation -->
      {#if race.candidates.length > 1}
        <div class="candidate-nav">
          <p class="nav-label">Jump to candidate:</p>
          <div class="nav-links">
            {#each race.candidates as candidate, index}
              <a 
                href="#{candidate.name.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '')}"
                class="nav-link"
              >
                {candidate.name}
              </a>
            {/each}
          </div>
        </div>
      {/if}
      
      <div class="candidate-grid">
        {#each race.candidates as candidate}
          <CandidateCard {candidate} />
        {/each}
      </div>
    </section>

    <!-- Data Note -->
    <div class="data-note">
      <p class="data-note-title">
        {usingFallbackData ? "Sample Data Information" : "Data Analysis Information"}
      </p>
      <p class="data-note-text">
        {#if usingFallbackData}
          This is sample data for demonstration purposes. The actual race data is currently unavailable.
        {:else}
          Data compiled from public sources and analyzed using AI. Last updated {new Date(
            race.updated_utc
          ).toLocaleDateString()}. Visit candidate websites for the most current information.
        {/if}
      </p>
    </div>

    <!-- Back to Top Link -->
    {#if race.candidates.length > 2}
      <div class="back-to-top">
        <button 
          class="back-to-top-link"
          on:click={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18" />
          </svg>
          Back to Top
        </button>
      </div>
    {/if}
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
    @apply ml-3 text-lg text-gray-600;
  }

  .error-box {
    @apply bg-red-50 border border-red-200 rounded-lg p-6 text-center;
  }

  .error-title {
    @apply text-2xl font-bold text-red-800 mb-2;
  }

  .error-button {
    @apply mt-4 bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700;
  }

  :global(.header-card) {
    @apply p-4 sm:p-6 mb-6 sm:mb-8 shadow-sm;
  }

  .header-title {
    @apply text-2xl sm:text-3xl lg:text-4xl font-bold text-gray-900 mb-4;
  }

  .header-meta {
    @apply flex flex-col sm:flex-row sm:flex-wrap items-start sm:items-center gap-3 sm:gap-6 text-gray-600;
  }

  .info-row {
    @apply flex items-center gap-2;
  }

  .model-label {
    @apply mt-4 flex items-center gap-2 text-sm text-gray-500;
  }

  .model-tag {
    @apply bg-gray-100 px-2 py-1 rounded;
  }

  .candidates-title {
    @apply text-xl sm:text-2xl font-semibold text-gray-900 mb-4 sm:mb-6;
  }

  .candidate-nav {
    @apply mb-6 sm:mb-8 p-3 sm:p-4 bg-gray-50 rounded-lg border border-gray-200;
  }

  .nav-label {
    @apply text-xs sm:text-sm font-medium text-gray-700 mb-2 sm:mb-3;
  }

  .nav-links {
    @apply flex flex-wrap gap-1 sm:gap-2;
  }

  .nav-link {
    @apply px-2 sm:px-3 py-1 sm:py-2 bg-white border border-gray-300 rounded-md text-xs sm:text-sm font-medium text-gray-700 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors duration-200;
  }

  .candidate-grid {
    @apply grid gap-6 sm:gap-8 justify-items-stretch;
  }

  .data-note {
    @apply mt-8 sm:mt-12 bg-blue-50 border border-blue-200 rounded-lg p-4 sm:p-6 text-center;
  }

  .data-note-title {
    @apply text-blue-800 font-medium mb-2 text-sm sm:text-base;
  }

  .data-note-text {
    @apply text-blue-700 text-xs sm:text-sm;
  }

  .fallback-notice {
    @apply bg-yellow-50 border border-yellow-200 rounded-lg p-3 sm:p-4 mb-6 sm:mb-8;
  }

  .fallback-content {
    @apply flex items-start gap-2 sm:gap-3;
  }

  .fallback-title {
    @apply font-medium text-yellow-800 text-sm sm:text-base;
  }

  .fallback-text {
    @apply text-yellow-700 text-xs sm:text-sm mt-1;
  }

  .back-to-top {
    @apply mt-8 text-center;
  }

  .back-to-top-link {
    @apply inline-flex items-center gap-2 text-gray-600 hover:text-blue-600 font-medium transition-colors duration-200 border-none bg-transparent cursor-pointer;
  }
</style>
