<script lang="ts">
  import type { PageData } from "./$types";
  import type { RaceSummary } from "$lib/types";

  export let data: PageData;

  let searchQuery = "";
  let filteredRaces: RaceSummary[] = [];

  // Reactive statement to filter races based on search query
  $: {
    if (!searchQuery.trim()) {
      filteredRaces = data.races;
    } else {
      const query = searchQuery.toLowerCase();
      filteredRaces = data.races.filter(race =>
        race.title?.toLowerCase().includes(query) ||
        race.office?.toLowerCase().includes(query) ||
        race.jurisdiction?.toLowerCase().includes(query) ||
        race.candidates.some(candidate =>
          candidate.name.toLowerCase().includes(query) ||
          candidate.party?.toLowerCase().includes(query)
        )
      );
    }
  }

  function formatElectionDate(dateString: string): string {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  }

  function getRaceUrl(raceId: string): string {
    return `/races/${raceId}`;
  }
</script>

<svelte:head>
  <title>Smarter.vote - AI-Powered Election Information</title>
  <meta
    name="description"
    content="Compare candidates on key issues with AI-powered analysis from public sources."
  />
</svelte:head>

<div class="container mx-auto px-4 py-8 sm:py-12 max-w-6xl">
  <!-- Hero Section -->
  <header class="text-center mb-8 sm:mb-12">
    <h1 class="text-3xl sm:text-4xl lg:text-5xl font-bold text-gray-900 mb-4">Smarter.vote</h1>
    <p class="text-lg sm:text-xl text-gray-600 mb-6 sm:mb-8">
      AI-powered candidate comparison on the issues that matter
    </p>
    <p class="text-sm sm:text-base text-gray-500 max-w-2xl mx-auto px-4">
      We analyze candidates' positions from public sources using multiple AI
      models to provide clear, unbiased comparisons of where they stand on key
      issues.
    </p>
  </header>

  <!-- Search Bar -->
  <div class="flex justify-end mb-6">
    <div class="relative w-full max-w-md">
      <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
        <svg class="h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
        </svg>
      </div>
      <input
        type="text"
        bind:value={searchQuery}
        placeholder="Search races, candidates, or locations..."
        class="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg leading-5 bg-white placeholder-gray-500 focus:outline-none focus:placeholder-gray-400 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
      />
    </div>
  </div>

  <!-- All Races Section -->
  <section class="bg-white rounded-lg shadow-sm">
    <div class="p-4 sm:p-6 border-b border-gray-200">
      <h2 class="text-xl sm:text-2xl font-semibold text-gray-900">
        Available Races ({filteredRaces.length})
      </h2>
      <p class="text-sm text-gray-600 mt-1">
        {searchQuery ? `Showing results for "${searchQuery}"` : 'Browse all available race analyses'}
      </p>
    </div>

    <div class="h-96 overflow-y-auto">
      {#if filteredRaces.length === 0}
        <div class="p-8 text-center text-gray-500">
          {#if searchQuery}
            <svg class="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 12h6m-6-4h6m2 5.291A7.962 7.962 0 0112 15c-2.34 0-4.47-.881-6.08-2.329C7.76 10.22 9.77 8 12.16 8c1.311 0 2.52.375 3.546 1.022M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
            <p class="text-lg font-medium">No races found</p>
            <p class="mt-2">Try adjusting your search terms or browse all available races.</p>
          {:else}
            <svg class="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 4V2a1 1 0 011-1h8a1 1 0 011 1v2h4a1 1 0 110 2h-1v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6H3a1 1 0 010-2h4zM9 6h6v12H9V6z"/>
            </svg>
            <p class="text-lg font-medium">No races available</p>
            <p class="mt-2">Check back later for new race analyses.</p>
          {/if}
        </div>
      {:else}
        <div class="divide-y divide-gray-200">
          {#each filteredRaces as race (race.id)}
            <div class="p-4 sm:p-6 hover:bg-gray-50 transition-colors">
              <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between">
                <div class="mb-4 sm:mb-0">
                  <h3 class="text-lg font-semibold text-gray-900 mb-2">
                    {race.title || `${race.office || 'Race'} - ${race.jurisdiction || 'Unknown'}`}
                  </h3>
                  <div class="flex flex-wrap gap-2 text-sm text-gray-600 mb-2">
                    {#if race.office}
                      <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        {race.office}
                      </span>
                    {/if}
                    {#if race.jurisdiction}
                      <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                        {race.jurisdiction}
                      </span>
                    {/if}
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                      {formatElectionDate(race.election_date)}
                    </span>
                  </div>
                  <div class="text-sm text-gray-600">
                    <strong>Candidates:</strong>
                    {#each race.candidates as candidate, index}
                      <span class="font-medium">{candidate.name}</span>{#if candidate.party} ({candidate.party}){/if}{#if index < race.candidates.length - 1}, {/if}
                    {/each}
                  </div>
                  <div class="text-xs text-gray-500 mt-1">
                    Last updated: {new Date(race.updated_utc).toLocaleDateString()}
                  </div>
                </div>
                <div class="flex-shrink-0">
                  <a
                    href={getRaceUrl(race.id)}
                    class="inline-flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
                  >
                    Compare Candidates
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
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                  </a>
                </div>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </section>

  <!-- How It Works -->
  <section class="mt-12 mb-8 sm:mb-12">
    <h2 class="text-xl sm:text-2xl font-semibold text-gray-900 mb-4 sm:mb-6 text-center">
      How It Works
    </h2>
    <div class="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
      <div class="text-center">
        <div
          class="bg-blue-100 rounded-full w-12 h-12 sm:w-16 sm:h-16 flex items-center justify-center mx-auto mb-3 sm:mb-4"
        >
          <svg
            class="w-6 h-6 sm:w-8 sm:h-8 text-blue-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>
        <h3 class="font-semibold text-gray-900 mb-2 text-sm sm:text-base">Discover Sources</h3>
        <p class="text-gray-600 text-xs sm:text-sm">
          We find and analyze candidate websites, speeches, voting records, and
          public statements.
        </p>
      </div>
      <div class="text-center">
        <div
          class="bg-green-100 rounded-full w-12 h-12 sm:w-16 sm:h-16 flex items-center justify-center mx-auto mb-3 sm:mb-4"
        >
          <svg
            class="w-6 h-6 sm:w-8 sm:h-8 text-green-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
            />
          </svg>
        </div>
        <h3 class="font-semibold text-gray-900 mb-2 text-sm sm:text-base">AI Analysis</h3>
        <p class="text-gray-600 text-xs sm:text-sm">
          Multiple AI models analyze the content and extract positions on key
          issues with confidence ratings.
        </p>
      </div>
      <div class="text-center sm:col-span-2 lg:col-span-1">
        <div
          class="bg-purple-100 rounded-full w-12 h-12 sm:w-16 sm:h-16 flex items-center justify-center mx-auto mb-3 sm:mb-4"
        >
          <svg
            class="w-6 h-6 sm:w-8 sm:h-8 text-purple-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            />
          </svg>
        </div>
        <h3 class="font-semibold text-gray-900 mb-2 text-sm sm:text-base">Clear Comparison</h3>
        <p class="text-gray-600 text-xs sm:text-sm">
          Clean, side-by-side comparison of candidate positions with source
          links and confidence indicators.
        </p>
      </div>
    </div>
  </section>

  <!-- Key Features -->
  <section class="bg-white rounded-lg shadow-sm p-4 sm:p-8">
    <h2 class="text-xl sm:text-2xl font-semibold text-gray-900 mb-4 sm:mb-6 text-center">
      Why Smarter.vote?
    </h2>
    <div class="grid gap-4 sm:gap-6 sm:grid-cols-2">
      <div class="flex items-start gap-3">
        <div
          class="bg-green-100 rounded-full w-8 h-8 flex items-center justify-center flex-shrink-0 mt-1"
        >
          <svg
            class="w-4 h-4 text-green-600"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fill-rule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clip-rule="evenodd"
            />
          </svg>
        </div>
        <div>
          <h3 class="font-semibold text-gray-900 mb-1 text-sm sm:text-base">Unbiased Analysis</h3>
          <p class="text-gray-600 text-xs sm:text-sm">
            AI analyzes public sources without political bias, presenting facts
            clearly.
          </p>
        </div>
      </div>
      <div class="flex items-start gap-3">
        <div
          class="bg-green-100 rounded-full w-8 h-8 flex items-center justify-center flex-shrink-0 mt-1"
        >
          <svg
            class="w-4 h-4 text-green-600"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fill-rule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clip-rule="evenodd"
            />
          </svg>
        </div>
        <div>
          <h3 class="font-semibold text-gray-900 mb-1 text-sm sm:text-base">Source Transparency</h3>
          <p class="text-gray-600 text-xs sm:text-sm">
            Every position includes links to original sources and confidence
            ratings.
          </p>
        </div>
      </div>
      <div class="flex items-start gap-3">
        <div
          class="bg-green-100 rounded-full w-8 h-8 flex items-center justify-center flex-shrink-0 mt-1"
        >
          <svg
            class="w-4 h-4 text-green-600"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fill-rule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clip-rule="evenodd"
            />
          </svg>
        </div>
        <div>
          <h3 class="font-semibold text-gray-900 mb-1 text-sm sm:text-base">
            Comprehensive Coverage
          </h3>
          <p class="text-gray-600 text-xs sm:text-sm">
            Analysis covers 11 key issue areas from healthcare to climate
            policy.
          </p>
        </div>
      </div>
      <div class="flex items-start gap-3">
        <div
          class="bg-green-100 rounded-full w-8 h-8 flex items-center justify-center flex-shrink-0 mt-1"
        >
          <svg
            class="w-4 h-4 text-green-600"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fill-rule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clip-rule="evenodd"
            />
          </svg>
        </div>
        <div>
          <h3 class="font-semibold text-gray-900 mb-1 text-sm sm:text-base">Always Up-to-Date</h3>
          <p class="text-gray-600 text-xs sm:text-sm">
            Information is continuously updated as new public statements emerge.
          </p>
        </div>
      </div>
    </div>
  </section>
</div>
