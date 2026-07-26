<script lang="ts">
  import type { ForecastTab } from "$lib/utils/forecast";

  export let activeTab: ForecastTab;
  export let holdovers: {
    state: string;
    party: "Democratic" | "Republican" | "Other";
    count: number;
  }[];

  let showHoldovers = false;
</script>

{#if activeTab !== "house"}
  <section
    class="bg-surface border border-stroke rounded-2xl shadow-sm overflow-hidden mt-6"
  >
    <!-- Toggle header -->
    <button
      on:click={() => (showHoldovers = !showHoldovers)}
      class="w-full px-5 py-4 border-b border-stroke/40 flex items-center justify-between text-left hover:bg-surface-alt/30 transition-colors"
    >
      <div class="flex items-center gap-3">
        <h2 class="text-base font-bold text-content">
          {activeTab === "governors"
            ? "Governor Seats Not Up in 2026"
            : "Senate Seats Not Up in 2026"}
        </h2>
        <span
          class="bg-surface-alt text-content-muted font-bold text-xs px-2.5 py-0.5 rounded-full border border-stroke/60"
        >
          {holdovers.length}
          {activeTab === "governors" ? "states" : "seats"}
        </span>
      </div>
      <span class="text-xs text-blue-600 dark:text-blue-400 font-semibold">
        {showHoldovers ? "Hide List ^" : "Show List v"}
      </span>
    </button>

    {#if showHoldovers}
      <div class="p-5 bg-surface-alt/10">
        <p class="text-xs text-content-subtle mb-4">
          These seats are not up for election in 2026 and are factored into our
          control calculations based on current incumbent party representation.
        </p>
        <div
          class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3"
        >
          {#each holdovers as h}
            <div
              class="bg-surface border border-stroke/60 rounded-xl px-3 py-2 flex items-center justify-between shadow-sm"
            >
              <span class="text-xs font-bold text-content truncate pr-1"
                >{h.state}</span
              >
              <span
                class={`text-[10px] font-extrabold uppercase px-1.5 py-0.5 rounded-md border ${
                  h.party === "Democratic"
                    ? "bg-blue-500/10 text-blue-600 border-blue-500/20 dark:bg-blue-500/20 dark:text-blue-400"
                    : "bg-red-500/10 text-red-600 border-red-500/20 dark:bg-red-500/20 dark:text-red-400"
                }`}
              >
                {h.party === "Democratic" ? "D" : "R"}{h.count > 1
                  ? ` x${h.count}`
                  : ""}
              </span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </section>
{/if}
