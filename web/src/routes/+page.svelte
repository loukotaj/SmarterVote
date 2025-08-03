<script lang="ts">
  // Future: Add search functionality and featured races
</script>

<svelte:head>
  <title>Smarter.vote - AI-Powered Election Information</title>
  <meta
    name="description"
    content="Compare candidates on key issues with AI-powered analysis from public sources."
  />
</svelte:head>

<div class="container mx-auto px-4 py-12 max-w-4xl">
  <!-- Hero Section -->
  <header class="text-center mb-12">
    <h1 class="text-5xl font-bold text-gray-900 mb-4">Smarter.vote</h1>
    <p class="text-xl text-gray-600 mb-8">
      AI-powered candidate comparison on the issues that matter
    </p>
    <p class="text-gray-500 max-w-2xl mx-auto">
      We analyze candidates' positions from public sources using multiple AI
      models to provide clear, unbiased comparisons of where they stand on key
      issues.
    </p>
  </header>

  <!-- Sample Race (for demo) -->
  <section class="bg-white rounded-lg shadow-sm p-8 mb-8">
    <h2 class="text-2xl font-semibold text-gray-900 mb-6">Featured Race</h2>
    <div class="border border-gray-200 rounded-lg p-6">
      <h3 class="text-xl font-bold text-gray-900 mb-2">Missouri Senate 2024</h3>
      <p class="text-gray-600 mb-4">
        U.S. Senate • Missouri • Election: November 5, 2024
      </p>
      <a
        href="/races/mo-senate-2024"
        class="inline-flex items-center gap-2 bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 transition-colors"
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
  </section>

  <!-- How It Works -->
  <section class="mb-12">
    <h2 class="text-2xl font-semibold text-gray-900 mb-6 text-center">
      How It Works
    </h2>
    <div class="grid md:grid-cols-3 gap-6">
      <div class="text-center">
        <div
          class="bg-blue-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4"
        >
          <svg
            class="w-8 h-8 text-blue-600"
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
        <h3 class="font-semibold text-gray-900 mb-2">Discover Sources</h3>
        <p class="text-gray-600 text-sm">
          We find and analyze candidate websites, speeches, voting records, and
          public statements.
        </p>
      </div>
      <div class="text-center">
        <div
          class="bg-green-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4"
        >
          <svg
            class="w-8 h-8 text-green-600"
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
        <h3 class="font-semibold text-gray-900 mb-2">AI Analysis</h3>
        <p class="text-gray-600 text-sm">
          Multiple AI models analyze the content and extract positions on key
          issues with confidence ratings.
        </p>
      </div>
      <div class="text-center">
        <div
          class="bg-purple-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4"
        >
          <svg
            class="w-8 h-8 text-purple-600"
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
        <h3 class="font-semibold text-gray-900 mb-2">Clear Comparison</h3>
        <p class="text-gray-600 text-sm">
          Clean, side-by-side comparison of candidate positions with source
          links and confidence indicators.
        </p>
      </div>
    </div>
  </section>

  <!-- Key Features -->
  <section class="bg-white rounded-lg shadow-sm p-8">
    <h2 class="text-2xl font-semibold text-gray-900 mb-6 text-center">
      Why Smarter.vote?
    </h2>
    <div class="grid md:grid-cols-2 gap-6">
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
          <h3 class="font-semibold text-gray-900 mb-1">Unbiased Analysis</h3>
          <p class="text-gray-600 text-sm">
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
          <h3 class="font-semibold text-gray-900 mb-1">Source Transparency</h3>
          <p class="text-gray-600 text-sm">
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
          <h3 class="font-semibold text-gray-900 mb-1">
            Comprehensive Coverage
          </h3>
          <p class="text-gray-600 text-sm">
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
          <h3 class="font-semibold text-gray-900 mb-1">Always Up-to-Date</h3>
          <p class="text-gray-600 text-sm">
            Information is continuously updated as new public statements emerge.
          </p>
        </div>
      </div>
    </div>
  </section>
</div>
