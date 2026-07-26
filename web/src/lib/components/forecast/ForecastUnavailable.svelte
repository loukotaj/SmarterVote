<!--
  Empty-state card shown when there are no races and no chamber forecast data
  available at all (as opposed to simply having no forecasts for the active
  tab, which is handled inline where the race list is rendered).
-->
<div
  class="max-w-2xl mx-auto my-16 p-8 bg-surface-alt border border-stroke/80 rounded-2xl text-center space-y-4"
>
  <div
    class="w-12 h-12 bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 rounded-full flex items-center justify-center mx-auto animate-pulse"
  >
    <svg
      class="w-6 h-6"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
      />
    </svg>
  </div>
  <h2 class="text-lg font-black text-content text-center">
    Forecast Data Unavailable
  </h2>
  <p
    class="text-xs text-content-muted leading-relaxed font-semibold max-w-sm mx-auto text-center"
  >
    We are currently updating our election models. Please check back shortly for
    the latest projections.
  </p>
</div>
