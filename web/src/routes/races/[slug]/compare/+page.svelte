<script lang="ts">
  import { browser } from "$app/environment";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import CandidateComparison from "$lib/components/compare/CandidateComparison.svelte";
  import { getDraftRace, getRace } from "$lib/api";
  import type { Candidate, Race } from "$lib/types";
  import { candidateSlug } from "$lib/utils/format";
  import { onMount } from "svelte";

  export let data: { prerenderedRace?: Race };

  let race: Race | null = data.prerenderedRace ?? null;
  let candidates: Candidate[] = race
    ? race.candidates.filter((candidate) => !candidate.withdrawn).slice(0, 2)
    : [];
  let loading = !race;
  let error: string | null = null;
  let isDraftPreview = false;

  $: slug = $page.params.slug as string;
  $: if (browser && race && $page) hydrateCandidates();

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
    } catch (caught) {
      if (hasPrerenderedRace && race) {
        loading = false;
        hydrateCandidates();
        return;
      }
      error =
        caught instanceof Error ? caught.message : "Failed to load race data";
    } finally {
      hydrateCandidates();
      loading = false;
    }
  });

  function hydrateCandidates() {
    if (!race || !browser) return;
    const selected = $page.url.searchParams.get("candidates");
    if (selected) {
      const slugs = selected.split(",");
      candidates = race.candidates.filter(
        (candidate) =>
          slugs.includes(candidateSlug(candidate.name)) && !candidate.withdrawn
      );
    }
    if (candidates.length === 0)
      candidates = race.candidates
        .filter((candidate) => !candidate.withdrawn)
        .slice(0, 2);
  }

  function toggleSelection(candidateName: string) {
    if (!race) return;
    const selectedSlug = candidateSlug(candidateName);
    const params = new URLSearchParams($page.url.searchParams);
    let current = params.get("candidates")?.split(",") ?? [];
    if (current.length === 0)
      current = race.candidates
        .filter((candidate) => !candidate.withdrawn)
        .slice(0, 2)
        .map((candidate) => candidateSlug(candidate.name));
    if (current.includes(selectedSlug)) {
      if (current.length > 1)
        current = current.filter((value) => value !== selectedSlug);
    } else current.push(selectedSlug);
    params.set("candidates", current.join(","));
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
  <meta property="og:type" content="article" />
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

<div class="container mx-auto max-w-7xl px-4 py-6 sm:py-8">
  <header
    class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
  >
    <div>
      <nav class="mb-1 text-xs uppercase tracking-wide text-content-subtle">
        <a href="/" class="hover:text-content">Home</a> &middot;
        <a
          href="/races/{slug}{isDraftPreview ? '?draft=true' : ''}"
          class="hover:text-content">Race Detail</a
        >
        &middot; <span class="text-content-muted">Compare</span>
      </nav>
      <h1
        class="text-2xl font-extrabold tracking-tight text-content sm:text-3xl"
      >
        Compare Candidates
      </h1>
      {#if race}<p class="mt-1 text-sm text-content-muted">
          {race.office}{race.district ? ` (${race.district})` : ""} &bull; {race.jurisdiction}
        </p>{/if}
    </div>
    <a
      href="/races/{slug}{isDraftPreview ? '?draft=true' : ''}"
      class="inline-flex items-center gap-1.5 rounded-lg border border-stroke px-4 py-2 text-sm font-semibold text-content no-underline transition-colors hover:bg-surface-alt"
      >← Back to Race Overview</a
    >
  </header>

  {#if loading}
    <div class="space-y-6">
      <div
        class="h-16 animate-pulse rounded-xl border border-stroke bg-surface"
      />
      <div
        class="h-96 animate-pulse rounded-xl border border-stroke bg-surface"
      />
    </div>
  {:else if error}
    <div
      class="rounded-lg border border-red-200 bg-red-50 p-6 text-center dark:border-red-800 dark:bg-red-950/30"
    >
      <h2 class="mb-2 text-xl font-bold text-red-800 dark:text-red-200">
        Error
      </h2>
      <p class="text-red-600 dark:text-red-400">{error}</p>
      <a
        href="/races/{slug}"
        class="mt-4 inline-block font-semibold text-blue-600 underline dark:text-blue-400"
        >Return to Race Overview</a
      >
    </div>
  {:else if race && candidates.length === 0}
    <div
      class="rounded-xl border border-stroke bg-surface p-8 text-center text-content-subtle"
    >
      <p class="text-lg font-semibold text-content">No Candidates Selected</p>
      <p class="mt-2 text-sm">
        Please select candidates from the race detail page to compare them.
      </p>
      <a
        href="/races/{slug}"
        class="btn-primary mt-4 inline-flex text-sm font-semibold no-underline"
        >Go Select Candidates</a
      >
    </div>
  {:else if race}
    <CandidateComparison
      {race}
      {candidates}
      {isDraftPreview}
      onToggle={toggleSelection}
    />
  {/if}
</div>
