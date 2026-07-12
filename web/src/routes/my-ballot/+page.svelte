<script lang="ts">
  import ElectionLookup from "$lib/components/home/ElectionLookup.svelte";
  import type { PageData } from "./$types";
  export let data: PageData;
</script>

<svelte:head>
  <title>Find My Elections | Smarter.Vote</title>
  <meta
    name="description"
    content="Use your address to find the national election guides that apply to you. Smarter.Vote does not store your address."
  />
  <link rel="canonical" href="https://smarter.vote/my-ballot/" />
  <meta name="robots" content="noindex, nofollow" />
</svelte:head>

<div class="relative isolate min-h-[calc(100svh-4rem)] overflow-hidden bg-page">
  <div
    class="pointer-events-none absolute inset-0 -z-10 opacity-70 dark:opacity-30"
    aria-hidden="true"
  >
    <div
      class="absolute -left-40 top-8 h-96 w-96 rounded-full bg-blue-100 blur-3xl dark:bg-blue-950"
    />
    <div
      class="absolute -right-32 bottom-0 h-80 w-80 rounded-full bg-sky-100 blur-3xl dark:bg-sky-950"
    />
    <svg
      class="absolute inset-0 h-full w-full text-blue-900/[0.035] dark:text-blue-100/[0.035]"
      viewBox="0 0 1200 800"
      preserveAspectRatio="xMidYMid slice"
    >
      <path
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        d="M-80 590C120 480 205 655 380 526S650 345 822 428s282-34 460-182M-60 312C142 218 282 376 446 248S715 84 902 170s255 8 390-73"
      />
    </svg>
  </div>

  <div
    class="mx-auto grid min-h-[calc(100svh-4rem)] max-w-7xl items-center gap-8 px-5 py-8 sm:gap-12 sm:px-8 sm:py-16 lg:grid-cols-[0.8fr_1.2fr] lg:px-12 lg:py-20"
  >
    <header class="max-w-xl">
      <a
        href="/"
        class="inline-flex items-center gap-2 text-sm font-semibold text-blue-700 transition hover:text-blue-900 dark:text-blue-300 dark:hover:text-blue-100"
        ><span aria-hidden="true">←</span> Back to Smarter.Vote</a
      >
      <p
        class="mt-6 text-xs font-bold uppercase tracking-[0.2em] text-blue-600 sm:mt-12 dark:text-blue-400"
      >
        Your election guide
      </p>
      <h1
        class="mt-4 text-4xl font-bold tracking-tight text-content sm:text-5xl lg:text-6xl"
      >
        Find the races that apply to you.
      </h1>
      <p class="mt-6 max-w-lg text-lg leading-8 text-content-muted">
        We use your address only to identify your congressional district, then
        match it with our published House, Senate, and governor research.
      </p>
      <div
        class="mt-10 hidden border-l-2 border-blue-200 pl-5 sm:block dark:border-blue-800"
      >
        <p class="font-semibold text-content">Private by design</p>
        <p class="mt-1 text-sm leading-6 text-content-muted">
          Your address goes directly to the U.S. Census Geocoder. Smarter.Vote
          does not receive, save, or add it to the page URL.
        </p>
      </div>
    </header>
    <ElectionLookup races={data.races ?? []} />
  </div>
</div>
