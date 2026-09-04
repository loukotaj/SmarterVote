<script lang="ts">
  import HowItWorks from "$lib/components/home/HowItWorks.svelte";
  import InteractiveRaceCompare from "$lib/components/home/InteractiveRaceCompare.svelte";
  import TrustPrinciples from "$lib/components/home/TrustPrinciples.svelte";
  import type { PageData } from "./$types";
  export let data: PageData;
</script>

<svelte:head>
  <title>Smarter.Vote | Know your candidates</title>
  <meta
    name="description"
    content="Explore sourced, nonpartisan research for national elections. Compare candidates, inspect original sources, and understand the federal races on your ballot."
  />
  <link rel="canonical" href="https://smarter.vote/" />
  <meta property="og:type" content="website" />
  <meta property="og:url" content="https://smarter.vote/" />
  <meta property="og:title" content="Smarter.Vote | Know your candidates" />
  <meta
    property="og:description"
    content="Sourced, nonpartisan candidate research with uncertainty and original evidence kept visible."
  />
  <meta property="og:image" content="https://smarter.vote/og-image.png" />
  <meta name="twitter:card" content="summary_large_image" />
</svelte:head>

<div class="overflow-hidden">
  <section
    class="relative border-b border-stroke bg-surface py-10 sm:py-12 lg:py-14"
  >
    <div
      class="absolute inset-0 opacity-60 [background-image:linear-gradient(to_right,theme(colors.blue.100)_1px,transparent_1px),linear-gradient(to_bottom,theme(colors.blue.100)_1px,transparent_1px)] [background-size:56px_56px] [mask-image:linear-gradient(to_right,black,transparent_75%)] dark:opacity-10"
      aria-hidden="true"
    ></div>
    <div
      class="relative mx-auto grid w-full max-w-[90rem] items-start gap-9 px-4 sm:px-6 lg:grid-cols-[minmax(360px,0.72fr)_minmax(680px,1.28fr)] lg:gap-10 lg:px-10 xl:gap-16"
    >
      <div class="lg:sticky lg:top-32 lg:py-7">
        <div class="flex items-center gap-3">
          <span class="h-px w-9 bg-blue-600"></span>
          <p
            class="text-xs font-bold uppercase tracking-[0.24em] text-blue-600 dark:text-blue-400"
          >
            Know your candidates
          </p>
        </div>
        <h1
          class="mt-6 max-w-2xl text-5xl font-extrabold leading-[.98] tracking-[-0.045em] text-content sm:text-6xl lg:text-7xl"
        >
          Understand your ballot.
        </h1>
        <p
          class="mt-6 max-w-xl text-lg leading-8 text-content-muted sm:text-xl"
        >
          Smarter.Vote turns candidate records, issue positions, and original
          sources into clear, nonpartisan election research you can examine for
          yourself.
        </p>
        <div
          class="mt-9 grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2"
        >
          <a
            href="/my-ballot/"
            class="group rounded-xl bg-blue-600 px-5 py-4 text-white shadow-lg shadow-blue-600/20 transition hover:-translate-y-1 hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
          >
            <span class="flex items-center justify-between font-extrabold"
              >Explore my ballot <span
                class="transition group-hover:translate-x-1">→</span
              ></span
            >
            <span class="mt-1 block text-sm text-blue-100"
              >Find the national races tied to your address</span
            >
          </a>
          <a
            href="/elections/"
            class="group rounded-xl border border-stroke bg-surface px-5 py-4 text-content shadow-sm transition hover:-translate-y-1 hover:border-blue-400 hover:shadow-md"
          >
            <span class="flex items-center justify-between font-extrabold"
              >Browse all elections <span
                class="text-blue-600 transition group-hover:translate-x-1"
                >→</span
              ></span
            >
            <span class="mt-1 block text-sm text-content-muted"
              >Explore every published candidate guide</span
            >
          </a>
        </div>
      </div>
      <div class="min-w-0 pb-4 lg:pt-2">
        <InteractiveRaceCompare races={data.gradeARaces} />
      </div>
    </div>
  </section>

  <TrustPrinciples />
  <HowItWorks />
  <section
    class="relative overflow-hidden bg-blue-600 py-24 text-white sm:py-32"
  >
    <div
      class="absolute inset-0 opacity-20 [background-image:radial-gradient(circle_at_20%_20%,white_1px,transparent_1px)] [background-size:30px_30px]"
      aria-hidden="true"
    ></div>
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
