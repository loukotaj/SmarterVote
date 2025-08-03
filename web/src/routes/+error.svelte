<svelte:head>
  <title>Page Not Found | Smarter.vote</title>
  <meta
    name="description"
    content="The page you're looking for could not be found."
  />
</svelte:head>

<div class="container mx-auto px-4 py-12 max-w-4xl text-center">
  <div class="bg-white rounded-lg shadow-sm p-12">
    <div class="mb-8">
      <svg
        class="w-24 h-24 text-gray-400 mx-auto mb-4"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M9.172 16.172a4 4 0 015.656 0M9 12h6m-6-4h6m2 5.291A7.962 7.962 0 0112 15c-2.34 0-4.29-1.908-4.29-4.29C7.71 8.368 9.66 6.46 12 6.46s4.29 1.908 4.29 4.29A7.962 7.962 0 0112 15z"
        />
      </svg>
      <h1 class="text-4xl font-bold text-gray-900 mb-4">Page Not Found</h1>
      <p class="text-xl text-gray-600 mb-8">
        Sorry, we couldn't find the page you're looking for.
      </p>
    </div>

    <div class="space-y-4">
      <a
        href="/"
        class="inline-flex items-center gap-2 bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 transition-colors"
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
    </div>

    <div class="mt-8 text-sm text-gray-500">
      <p>
        If you think this is an error, please check the URL or try searching for
        the content you need.
      </p>
    </div>
  </div>
</div>
