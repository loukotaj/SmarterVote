<script lang="ts">
  import type { ChamberForecastDetails } from "$lib/types";
  import type { ForecastTab } from "$lib/utils/forecast";

  export let activeTab: ForecastTab;
  export let chamberSummary: ChamberForecastDetails | undefined;
  export let chamberNarrative: string;

  let expanded = false;
  $: hasAdditionalAnalysis = Boolean(
    chamberSummary?.why_party_favored ||
      chamberSummary?.opposing_party_path ||
      chamberSummary?.key_uncertainty,
  );
  $: summary =
    chamberSummary?.bottom_line ||
    chamberNarrative ||
    `Projections indicate a highly competitive cycle for the ${
      activeTab === "governors"
        ? "Governors"
        : activeTab === "senate"
          ? "Senate"
          : "House"
    }.`;
  $: panelId = `forecast-outlook-${activeTab}`;
</script>

<section
  class="overflow-hidden rounded-2xl border border-stroke bg-surface shadow-sm"
>
  <div
    class="flex flex-col gap-3 border-b border-stroke/40 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
  >
    <div>
      <h3 class="text-base font-bold uppercase tracking-wider text-content">
        Outlook & Analysis
      </h3>
      <p class="mt-1 text-xs font-semibold text-content-subtle">
        Structured assessment of the {activeTab === "house"
          ? "House"
          : activeTab === "senate"
            ? "Senate"
            : "Governor"} map
      </p>
    </div>
    {#if hasAdditionalAnalysis}
      <button
        type="button"
        on:click={() => (expanded = !expanded)}
        aria-expanded={expanded}
        aria-controls={panelId}
        class="inline-flex min-h-11 shrink-0 items-center justify-center rounded-lg border border-stroke bg-surface-alt px-4 py-2 text-xs font-bold text-blue-600 hover:border-blue-400 dark:text-blue-400"
      >
        {expanded ? "Hide full analysis" : "Show full analysis"}
      </button>
    {/if}
  </div>

  <div class="px-5 py-4">
    <p class="text-sm font-semibold leading-relaxed text-content">{summary}</p>
  </div>

  {#if hasAdditionalAnalysis}
    <div
      id={panelId}
      class:hidden={!expanded}
      class="grid grid-cols-1 gap-4 border-t border-stroke/40 bg-surface-alt/10 p-5 md:grid-cols-3"
    >
      {#if chamberSummary?.why_party_favored}
        <article class="rounded-xl border border-stroke bg-surface p-4">
          <h4
            class="text-xs font-black uppercase tracking-wider text-red-600 dark:text-red-400"
          >
            Why {chamberSummary.control_party === "Democratic"
              ? "Democrats"
              : "Republicans"} Are Favored
          </h4>
          <p
            class="mt-2 text-xs font-semibold leading-relaxed text-content-muted"
          >
            {chamberSummary.why_party_favored}
          </p>
        </article>
      {/if}

      {#if chamberSummary?.opposing_party_path}
        <article class="rounded-xl border border-stroke bg-surface p-4">
          <h4
            class="text-xs font-black uppercase tracking-wider text-blue-600 dark:text-blue-400"
          >
            {chamberSummary.control_party === "Democratic"
              ? "Republican"
              : "Democratic"} Path to Control
          </h4>
          <p
            class="mt-2 text-xs font-semibold leading-relaxed text-content-muted"
          >
            {chamberSummary.opposing_party_path}
          </p>
        </article>
      {/if}

      {#if chamberSummary?.key_uncertainty}
        <article class="rounded-xl border border-stroke bg-surface p-4">
          <h4
            class="text-xs font-black uppercase tracking-wider text-yellow-600 dark:text-yellow-400"
          >
            Key Risk & Uncertainty
          </h4>
          <p
            class="mt-2 text-xs font-semibold leading-relaxed text-content-muted"
          >
            {chamberSummary.key_uncertainty}
          </p>
        </article>
      {/if}
    </div>
  {/if}
</section>
