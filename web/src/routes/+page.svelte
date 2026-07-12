<script lang="ts">
  import FeaturedElections from "$lib/components/home/FeaturedElections.svelte";
  import HeroResearchVisual from "$lib/components/home/HeroResearchVisual.svelte";
  import HowItWorks from "$lib/components/home/HowItWorks.svelte";
  import ResearchPreview from "$lib/components/home/ResearchPreview.svelte";
  import TrustPrinciples from "$lib/components/home/TrustPrinciples.svelte";
  import type { PageData } from "./$types";
  export let data: PageData;
</script>

<svelte:head>
  <title>Smarter.Vote | Understand Every Race on Your Ballot</title>
  <meta
    name="description"
    content="Explore sourced, nonpartisan candidate and election research. Compare the evidence, inspect original sources, and understand every race on your ballot."
  />
  <link rel="canonical" href="https://smarter.vote/" />
  <meta property="og:type" content="website" /><meta
    property="og:url"
    content="https://smarter.vote/"
  />
  <meta
    property="og:title"
    content="Smarter.Vote | Understand every race on your ballot"
  />
  <meta
    property="og:description"
    content="Sourced, nonpartisan candidate research with uncertainty and original evidence kept visible."
  />
  <meta property="og:image" content="https://smarter.vote/og-image.png" /><meta
    name="twitter:card"
    content="summary_large_image"
  />
</svelte:head>

<div class="overflow-hidden">
  <section
    class="relative flex min-h-[calc(100svh-4rem)] items-center border-b border-stroke bg-surface py-20 sm:py-24"
  >
    <div
      class="absolute inset-0 opacity-60 [background-image:linear-gradient(to_right,theme(colors.blue.100)_1px,transparent_1px),linear-gradient(to_bottom,theme(colors.blue.100)_1px,transparent_1px)] [background-size:56px_56px] [mask-image:linear-gradient(to_right,black,transparent_75%)] dark:opacity-10"
      aria-hidden="true"
    />
    <div
      class="relative mx-auto grid w-full max-w-7xl items-center gap-16 px-4 sm:px-6 lg:grid-cols-[1fr_.9fr] lg:px-10"
    >
      <div>
        <div class="flex items-center gap-3">
          <span class="h-px w-9 bg-blue-600" />
          <p
            class="text-xs font-bold uppercase tracking-[0.24em] text-blue-600 dark:text-blue-400"
          >
            Know your candidates
          </p>
        </div>
        <h1
          class="mt-7 max-w-3xl text-5xl font-extrabold leading-[.98] tracking-[-0.045em] text-content sm:text-6xl lg:text-7xl"
        >
          Understand every race on your ballot.
        </h1>
        <p
          class="mt-7 max-w-xl text-lg leading-8 text-content-muted sm:text-xl"
        >
          Smarter.Vote turns candidate records, issue positions, and original
          sources into clear, nonpartisan election research you can examine for
          yourself.
        </p>
        <div class="mt-9 flex flex-col gap-3 sm:flex-row">
          <a
            href="/my-ballot/"
            class="inline-flex min-h-12 items-center justify-center rounded-md bg-blue-600 px-7 py-3 font-bold text-white shadow-lg shadow-blue-600/20 transition hover:-translate-y-0.5 hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
            >Explore my ballot <span class="ml-3">→</span></a
          >
          <a
            href="/elections/"
            class="inline-flex min-h-12 items-center justify-center rounded-md border border-stroke bg-surface px-7 py-3 font-bold text-content transition hover:border-blue-400 hover:text-blue-600"
            >Browse all elections</a
          >
        </div>
      </div>
      <div class="pb-7 lg:pl-4">
        <HeroResearchVisual
          race={data.preview}
          summary={data.featuredRaces[0]}
        />
      </div>
    </div>
  </section>

  <TrustPrinciples />

  {#if data.preview}
    <ResearchPreview race={data.preview} />
  {:else}
    <section class="py-20 text-center sm:py-28">
      <p
        class="text-xs font-bold uppercase tracking-[0.24em] text-blue-600 dark:text-blue-400"
      >
        Explore the research
      </p>
      <h2
        class="mx-auto mt-4 max-w-2xl text-4xl font-bold tracking-tight text-content sm:text-5xl"
      >
        See the evidence side by side.
      </h2>
      <a
        href="/elections/"
        class="mt-8 inline-flex rounded-md bg-blue-600 px-7 py-3 font-bold text-white hover:bg-blue-700"
        >Browse published guides →</a
      >
    </section>
  {/if}

  <HowItWorks />
  <FeaturedElections races={data.featuredRaces} />

  <section
    class="relative overflow-hidden bg-blue-600 py-24 text-white sm:py-32"
  >
    <div
      class="absolute inset-0 opacity-20 [background-image:radial-gradient(circle_at_20%_20%,white_1px,transparent_1px)] [background-size:30px_30px]"
      aria-hidden="true"
    />
    <div class="relative mx-auto max-w-4xl px-4 text-center sm:px-6">
      <p class="text-xs font-bold uppercase tracking-[0.24em] text-blue-100">
        Your ballot deserves a closer look
      </p>
      <h2 class="mt-5 text-4xl font-extrabold tracking-tight sm:text-6xl">
        Know what you’re voting on.
      </h2>
      <p class="mx-auto mt-5 max-w-xl text-lg leading-8 text-blue-100">
        Start with your address. Continue with the evidence.
      </p>
      <a
        href="/my-ballot/"
        class="mt-9 inline-flex min-h-12 items-center rounded-md bg-white px-8 py-3 font-bold text-blue-700 shadow-xl transition hover:-translate-y-0.5 hover:bg-blue-50"
        >Find my elections <span class="ml-3">→</span></a
      >
    </div>
  </section>
</div>
