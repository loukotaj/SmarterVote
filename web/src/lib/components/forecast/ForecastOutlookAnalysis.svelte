<script lang="ts">
  import type { ChamberForecastDetails } from "$lib/types";
  import type { ForecastTab } from "$lib/utils/forecast";

  export let activeTab: ForecastTab;
  export let chamberSummary: ChamberForecastDetails | undefined;
  export let chamberNarrative: string;
</script>

<!-- Outlook & Analysis Section -->
<section class="space-y-4">
  <div class="flex items-center justify-between border-b border-stroke/20 pb-2">
    <h3 class="text-base font-bold uppercase text-content tracking-wider">
      Outlook & Analysis
    </h3>
    <span class="text-xs text-content-subtle font-semibold"
      >Structured assessment of the {activeTab === "house"
        ? "House"
        : activeTab === "senate"
          ? "Senate"
          : "Governor"} map</span
    >
  </div>

  {#if chamberSummary?.bottom_line || chamberSummary?.why_party_favored || chamberSummary?.opposing_party_path || chamberSummary?.key_uncertainty}
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <!-- Bottom Line -->
      {#if chamberSummary.bottom_line}
        <div
          class="bg-surface/80 border-2 border-blue-500/30 dark:border-blue-500/20 rounded-2xl p-5 shadow-sm relative overflow-hidden backdrop-blur-md"
        >
          <div
            class="absolute top-0 right-0 w-24 h-24 bg-blue-500/5 dark:bg-blue-500/10 rounded-bl-full pointer-events-none"
          ></div>
          <h4
            class="text-xs font-black uppercase text-blue-600 dark:text-blue-400 tracking-widest mb-2 flex items-center gap-1.5"
          >
            <svg
              class="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <circle cx="12" cy="12" r="10" />
              <circle cx="12" cy="12" r="6" />
              <circle cx="12" cy="12" r="2" />
            </svg> The Bottom Line
          </h4>
          <p class="text-sm font-semibold text-content leading-relaxed">
            {chamberSummary.bottom_line}
          </p>
        </div>
      {/if}

      <!-- Why Favored -->
      {#if chamberSummary.why_party_favored}
        <div
          class="bg-surface/60 border border-stroke rounded-2xl p-5 shadow-sm backdrop-blur-md"
        >
          <h4
            class="text-xs font-black uppercase text-red-600 dark:text-red-400 tracking-widest mb-2 flex items-center gap-1.5"
          >
            <svg
              class="w-4 h-4 text-red-600 dark:text-red-400 shrink-0"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              viewBox="0 0 24 24"
            >
              <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
              <polyline points="16 7 22 7 22 13" />
            </svg>
            Why {chamberSummary.control_party === "Democratic"
              ? "Democrats"
              : "Republicans"} Are Favored
          </h4>
          <p
            class="text-xs text-content-muted leading-relaxed font-medium font-semibold"
          >
            {chamberSummary.why_party_favored}
          </p>
        </div>
      {/if}

      <!-- Opposing Path -->
      {#if chamberSummary.opposing_party_path}
        <div
          class="bg-surface/60 border border-stroke rounded-2xl p-5 shadow-sm backdrop-blur-md"
        >
          <h4
            class="text-xs font-black uppercase text-blue-600 dark:text-blue-400 tracking-widest mb-2 flex items-center gap-1.5"
          >
            <svg
              class="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              viewBox="0 0 24 24"
            >
              <circle cx="6" cy="19" r="3" />
              <path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15" />
              <circle cx="18" cy="5" r="3" />
            </svg>
            {chamberSummary.control_party === "Democratic"
              ? "Republican"
              : "Democratic"} Path to Control
          </h4>
          <p
            class="text-xs text-content-muted leading-relaxed font-medium font-semibold"
          >
            {chamberSummary.opposing_party_path}
          </p>
        </div>
      {/if}

      <!-- Key Uncertainty -->
      {#if chamberSummary.key_uncertainty}
        <div
          class="bg-surface/60 border border-stroke rounded-2xl p-5 shadow-sm backdrop-blur-md"
        >
          <h4
            class="text-xs font-black uppercase text-yellow-600 dark:text-yellow-400 tracking-widest mb-2 flex items-center gap-1.5"
          >
            <svg
              class="w-4 h-4 text-yellow-600 dark:text-yellow-400 shrink-0"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              viewBox="0 0 24 24"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
              <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg> Key Risk & Uncertainty
          </h4>
          <p
            class="text-xs text-content-muted leading-relaxed font-medium font-semibold"
          >
            {chamberSummary.key_uncertainty}
          </p>
        </div>
      {/if}
    </div>
  {:else}
    <!-- Fallback narrative card -->
    <div
      class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md flex flex-col justify-between"
    >
      <div>
        <p class="text-sm font-medium text-content leading-relaxed">
          {chamberNarrative ||
            `Projections indicate a highly competitive cycle for the ${
              activeTab === "governors"
                ? "Governors"
                : activeTab === "senate"
                  ? "Senate"
                  : "House"
            }.`}
        </p>
      </div>
    </div>
  {/if}
</section>
