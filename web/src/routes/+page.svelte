<script lang="ts">
  import FeaturedElections from "$lib/components/home/FeaturedElections.svelte";
  import ElectionLookup from "$lib/components/home/ElectionLookup.svelte";
  import HowItWorks from "$lib/components/home/HowItWorks.svelte";
  import ImpactMetrics from "$lib/components/home/ImpactMetrics.svelte";
  import ResearchPreview from "$lib/components/home/ResearchPreview.svelte";
  import TrustPrinciples from "$lib/components/home/TrustPrinciples.svelte";
  import type { PageData } from "./$types";
  export let data: PageData;
</script>

<svelte:head>
  <title>Smarter.Vote | Sourced National Election Research</title>
  <meta
    name="description"
    content="Clear, sourced, nonpartisan candidate research for national elections, with visible sources, uncertainty, and update dates."
  />
  <link rel="canonical" href="https://smarter.vote/" />
  <meta property="og:type" content="website" />
  <meta property="og:url" content="https://smarter.vote/" />
  <meta
    property="og:title"
    content="Smarter.Vote | Understand the elections shaping the country"
  />
  <meta
    property="og:description"
    content="Clear, sourced, nonpartisan candidate research for national elections."
  />
  <meta property="og:image" content="https://smarter.vote/og-image.png" />
  <meta name="twitter:card" content="summary_large_image" />
</svelte:head>

<div>
  <section
    class="relative overflow-hidden border-b border-stroke bg-surface py-14 sm:py-20"
  >
    <div
      class="absolute inset-0 bg-gradient-to-br from-blue-50/80 via-transparent to-sky-50/50 dark:from-blue-950/20 dark:to-transparent"
      aria-hidden="true"
    />
    <div
      class="relative mx-auto grid max-w-6xl items-start gap-10 px-4 lg:grid-cols-[1.05fr_.95fr] lg:gap-14"
    >
      <div class="pt-4 text-left lg:pt-10">
        <p
          class="text-sm font-semibold uppercase tracking-[0.2em] text-blue-600 dark:text-blue-400"
        >
          2026 election research
        </p>
        <h1
          class="mt-5 max-w-3xl text-5xl font-extrabold tracking-tight text-content sm:text-6xl lg:text-7xl"
        >
          Know who’s running where you live.
        </h1>
        <p class="mt-6 max-w-xl text-lg leading-8 text-content-muted">
          Find the national elections that apply to your address, then compare
          candidates using sourced, nonpartisan research you can inspect.
        </p>
        <div
          class="mt-7 flex flex-wrap gap-x-6 gap-y-3 text-sm font-semibold text-content-muted"
        >
          <span>✓ Sources linked</span><span>✓ Uncertainty shown</span><span
            >✓ No candidate endorsements</span
          >
        </div>
      </div>
      <div><ElectionLookup races={data.nationalRaces} /></div>
    </div>
  </section>

  <FeaturedElections races={data.featuredRaces} />
  {#if data.preview}<ResearchPreview race={data.preview} />{:else}<section
      class="py-12 text-center"
    >
      <a
        href="/elections/"
        class="font-semibold text-blue-600 hover:underline dark:text-blue-400"
        >Browse published election research</a
      >
    </section>{/if}
  <HowItWorks />
  <TrustPrinciples />
  {#if data.metrics}<ImpactMetrics metrics={data.metrics} />{/if}

  <section class="py-16 sm:py-20">
    <div class="mx-auto max-w-4xl px-4 text-center">
      <h2 class="text-3xl font-bold text-content">
        Help expand clear election coverage
      </h2>
      <p class="mx-auto mt-4 max-w-2xl leading-7 text-content-muted">
        Support helps fund dependable data access, research and review,
        accessibility, and future translation. Supporters cannot influence
        findings or coverage treatment.
      </p>
      <div
        class="mt-7 flex flex-wrap justify-center gap-5 font-semibold text-blue-600 dark:text-blue-400"
      >
        <a href="/support/" class="hover:underline">Support Smarter.Vote</a><a
          href="/partners/"
          class="hover:underline">Partner with us</a
        >
      </div>
    </div>
  </section>
</div>
