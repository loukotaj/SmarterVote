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

  $: slug = $page.params.slug;

  onMount(async () => {
    try {
      race = await getRace(slug);
    } catch (err) {
      error = err instanceof Error ? err.message : "Failed to load race data";
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

<div class="container mx-auto px-4 py-8 max-w-7xl">
  {#if loading}
    <div class="flex items-center justify-center py-20">
      <div
        class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"
      />
      <span class="ml-3 text-lg text-gray-600">Loading race data...</span>
    </div>
  {:else if error}
    <div class="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
      <h2 class="text-2xl font-bold text-red-800 mb-2">Error Loading Race</h2>
      <p class="text-red-600">{error}</p>
      <button
        class="mt-4 bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
        on:click={() => window.location.reload()}
      >
        Try Again
      </button>
    </div>
  {:else if race}
    <!-- Race Header -->
    <Card tag="header" class="p-6 mb-8 shadow-sm">
      <h1 class="text-4xl font-bold text-gray-900 mb-4">{race.title}</h1>
      <div class="flex flex-wrap items-center gap-6 text-gray-600">
        <div class="flex items-center gap-2">
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
        <div class="flex items-center gap-2">
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
        <div class="flex items-center gap-2">
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
      <div class="mt-4 flex items-center gap-2 text-sm text-gray-500">
        <span>Analysis by:</span>
        {#each race.generator as model, i}
          <span class="bg-gray-100 px-2 py-1 rounded">{model}</span>
        {/each}
      </div>
    </Card>

    <!-- Candidates Section -->
    <section>
      <h2 class="text-2xl font-semibold text-gray-900 mb-6">Candidates</h2>
      <div
        class="grid gap-8 justify-items-center lg:grid-cols-2 lg:justify-items-stretch"
      >
        {#each race.candidates as candidate}
          <CandidateCard {candidate} />
        {/each}
      </div>
    </section>

    <!-- Data Note -->
    <div
      class="mt-12 bg-blue-50 border border-blue-200 rounded-lg p-6 text-center"
    >
      <p class="text-blue-800 font-medium mb-2">Data Analysis Information</p>
      <p class="text-blue-700 text-sm">
        Data compiled from public sources and analyzed using AI. Last updated {new Date(
          race.updated_utc
        ).toLocaleDateString()}. Visit candidate websites for the most current
        information.
      </p>
    </div>
  {/if}
</div>
