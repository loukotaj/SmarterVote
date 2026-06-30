<script lang="ts">
  import { createEventDispatcher } from "svelte";

  export let ballotpediaUrl: string | null = null;
  export let registerToVoteUrl: string = "https://vote.gov/register";
  export let howToVoteUrl: string = "https://vote.gov/";
  export let hasForecast = false;

  const dispatch = createEventDispatcher();
</script>

<div class="voter-resources">
  {#if ballotpediaUrl}
    <a
      href={ballotpediaUrl}
      target="_blank"
      rel="noopener noreferrer"
      class="voter-resource-btn voter-resource-btn--ballotpedia"
    >
      <svg
        class="w-5 h-5 shrink-0"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
      Election on Ballotpedia
      <svg
        class="w-3.5 h-3.5 shrink-0 opacity-60"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
        />
      </svg>
    </a>
  {/if}

  <a
    href={registerToVoteUrl}
    target="_blank"
    rel="noopener noreferrer"
    class="voter-resource-btn voter-resource-btn--register"
  >
    <svg
      class="w-5 h-5 shrink-0"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
      />
    </svg>
    Register to Vote
    <svg
      class="w-3.5 h-3.5 shrink-0 opacity-60"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
      />
    </svg>
  </a>

  <a
    href={howToVoteUrl}
    target="_blank"
    rel="noopener noreferrer"
    class="voter-resource-btn voter-resource-btn--howtovote"
  >
    <svg
      class="w-5 h-5 shrink-0"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
      />
    </svg>
    How to Vote
    <svg
      class="w-3.5 h-3.5 shrink-0 opacity-60"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
      />
    </svg>
  </a>

  {#if hasForecast}
    <a
      href="#forecast"
      class="voter-resource-btn voter-resource-btn--forecast"
      on:click={() => dispatch("jumpToForecast")}
    >
      <svg
        class="w-5 h-5 shrink-0"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M13 10V3L4 14h7v7l9-11h-7z"
        />
      </svg>
      Jump to Forecast
    </a>
  {/if}
</div>

<style lang="postcss">
  .voter-resources {
    @apply flex flex-wrap gap-3 mb-6;
  }

  .voter-resource-btn {
    @apply inline-flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm
           transition-all duration-200 no-underline shadow-sm;
  }

  .voter-resource-btn--ballotpedia {
    @apply bg-amber-50 border border-amber-300 text-amber-800
           hover:bg-amber-100 hover:border-amber-400 hover:shadow
           dark:bg-amber-900/20 dark:border-amber-700 dark:text-amber-300
           dark:hover:bg-amber-900/40 dark:hover:border-amber-600;
  }

  .voter-resource-btn--register {
    @apply bg-blue-600 border border-blue-600 text-white
           hover:bg-blue-700 hover:border-blue-700 hover:shadow
           dark:bg-blue-700 dark:border-blue-600
           dark:hover:bg-blue-600;
  }

  .voter-resource-btn--howtovote {
    @apply bg-green-600 border border-green-600 text-white
           hover:bg-green-700 hover:border-green-700 hover:shadow
           dark:bg-green-700 dark:border-green-600
           dark:hover:bg-green-600;
  }

  .voter-resource-btn--forecast {
    @apply bg-purple-500/10 text-purple-700 border border-purple-500/30
           hover:bg-purple-500/20 dark:bg-purple-950/20 dark:text-purple-300
           dark:border-purple-900/30;
  }
</style>
