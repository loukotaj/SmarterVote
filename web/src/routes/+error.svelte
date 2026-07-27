<script lang="ts">
  import { page } from "$app/stores";

  $: status = $page.status ?? 404;
  $: message =
    $page.error?.message ||
    (status === 404
      ? "Sorry, we couldn't find the page you're looking for."
      : "An unexpected error occurred while processing your request.");
  $: title = status === 404 ? "Page Not Found" : `Error ${status}`;
</script>

<svelte:head>
  <title>{title} | Smarter.vote</title>
  <meta name="description" content={message} />
</svelte:head>

<div class="container mx-auto px-4 py-12 max-w-4xl text-center">
  <div
    class="rounded-2xl border border-stroke bg-surface p-8 sm:p-12 shadow-sm"
  >
    <div class="mb-8">
      <svg
        class="w-20 h-20 mx-auto mb-4 text-content-subtle opacity-75"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="1.5"
          d="M9.172 16.172a4 4 0 015.656 0M9 12h6m-6-4h6m2 5.291A7.962 7.962 0 0112 15c-2.34 0-4.29-1.908-4.29-4.29C7.71 8.368 9.66 6.46 12 6.46s4.29 1.908 4.29 4.29A7.962 7.962 0 0112 15z"
        />
      </svg>
      <h1
        class="text-3xl sm:text-4xl font-extrabold tracking-tight text-content mb-3"
      >
        {title}
      </h1>
      <p class="text-base sm:text-lg text-content-muted max-w-md mx-auto">
        {message}
      </p>
    </div>

    <div class="flex flex-wrap items-center justify-center gap-3">
      <a
        href="/"
        class="inline-flex items-center gap-2 bg-blue-600 text-white px-5 py-2.5 rounded-xl font-semibold text-sm hover:bg-blue-700 transition-colors shadow-sm"
      >
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
            d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
          />
        </svg>
        Go Home
      </a>
      <a
        href="/elections/"
        class="inline-flex items-center gap-2 border border-stroke bg-surface-alt text-content px-5 py-2.5 rounded-xl font-semibold text-sm hover:bg-surface transition-colors"
      >
        Browse Elections &rarr;
      </a>
    </div>

    <div class="mt-8 text-xs text-content-subtle">
      <p>
        If you think this is an error, please check the URL or search for
        elections using the search bar above.
      </p>
    </div>
  </div>
</div>
