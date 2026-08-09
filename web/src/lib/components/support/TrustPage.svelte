<script lang="ts">
  export let title: string;
  export let description: string;
  export let path: string;
  export let eyebrow = "Smarter.Vote";
</script>

<svelte:head>
  <title>{title} | Smarter.Vote</title>
  <meta name="description" content={description} />
  <link rel="canonical" href={`https://smarter.vote${path}`} />
  <meta property="og:type" content="website" />
  <meta property="og:url" content={`https://smarter.vote${path}`} />
  <meta property="og:title" content={`${title} | Smarter.Vote`} />
  <meta property="og:description" content={description} />
  <meta property="og:image" content="https://smarter.vote/og-image.png" />
  <meta name="twitter:card" content="summary_large_image" />
</svelte:head>

<div class="mx-auto max-w-4xl px-4 py-10 sm:py-16 min-h-[calc(100vh-16rem)]">
  <header class="mb-10 max-w-3xl">
    <p
      class="mb-3 text-sm font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-500"
    >
      {eyebrow}
    </p>
    <h1 class="text-3xl font-bold tracking-tight text-content sm:text-4xl">
      {title}
    </h1>
    <p class="mt-4 text-lg leading-8 text-content-muted">{description}</p>
  </header>
  <div class="space-y-6 text-content-muted">
    <slot />
  </div>
</div>
