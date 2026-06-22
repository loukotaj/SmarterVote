<script lang="ts">
  import { onMount } from "svelte";
  import type { ChamberForecasts } from "$lib/types";
  import type { PipelineApiService } from "$lib/services/pipelineApiService";

  export let apiService: PipelineApiService;

  const DEFAULT_MODEL = "google/gemini-2.5-flash";

  let loading = true;
  let generating = false;
  let publishing = false;
  let error = "";
  let notice: { type: "success" | "error"; message: string } | null = null;
  let published: ChamberForecasts | null = null;
  let draft: ChamberForecasts | null = null;
  let model = DEFAULT_MODEL;

  function errorMessage(e: unknown): string {
    return e instanceof Error ? e.message : String(e);
  }

  function setNotice(type: "success" | "error", message: string) {
    notice = { type, message };
  }

  async function loadForecasts() {
    loading = true;
    error = "";
    notice = null;
    try {
      const [publishedResult, draftResult] = await Promise.allSettled([
        apiService.getPublishedChamberForecasts(),
        apiService.getChamberForecastDraft(),
      ]);
      published =
        publishedResult.status === "fulfilled" ? publishedResult.value : null;
      draft = draftResult.status === "fulfilled" ? draftResult.value : null;
    } catch (e) {
      error = errorMessage(e);
    } finally {
      loading = false;
    }
  }

  async function generateDraft() {
    if (
      !confirm(
        "Generate a new chamber forecast draft from current published race summaries?"
      )
    ) {
      return;
    }
    generating = true;
    notice = null;
    try {
      const result = await apiService.generateChamberForecastDraft(model);
      draft = result.forecast;
      setNotice("success", "Generated a new chamber forecast draft.");
    } catch (e) {
      setNotice("error", `Generate failed: ${errorMessage(e)}`);
    } finally {
      generating = false;
    }
  }

  async function publishDraft() {
    if (!confirm("Publish the current chamber forecast draft?")) return;
    publishing = true;
    notice = null;
    try {
      await apiService.publishChamberForecastDraft();
      await loadForecasts();
      setNotice("success", "Chamber forecast draft published.");
    } catch (e) {
      setNotice("error", `Publish failed: ${errorMessage(e)}`);
    } finally {
      publishing = false;
    }
  }

  onMount(loadForecasts);

  const chambersList: Array<"house" | "senate" | "governors"> = [
    "house",
    "senate",
    "governors",
  ];
</script>

<div class="space-y-6">
  <!-- Header Controls -->
  <div
    class="flex flex-wrap items-center justify-between gap-4 bg-surface border border-stroke p-4 rounded-lg"
  >
    <div>
      <h2 class="text-lg font-semibold text-content">Chamber Forecasts</h2>
      <p class="text-sm text-content-subtle">
        Compare published forecasts with recent drafts or trigger a new
        generation.
      </p>
    </div>
    <div class="flex flex-wrap items-center gap-3">
      <div class="flex items-center gap-2">
        <label
          for="model-select"
          class="text-sm text-content-subtle font-medium">Model:</label
        >
        <input
          id="model-select"
          type="text"
          bind:value={model}
          class="w-60 rounded border border-stroke bg-surface px-3 py-1.5 text-sm text-content focus:ring-1 focus:ring-blue-500 focus:outline-none"
        />
      </div>
      <button
        type="button"
        class="bg-surface hover:bg-surface-alt border border-stroke text-content rounded px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
        disabled={loading || generating}
        on:click={generateDraft}
      >
        {generating ? "Generating..." : "Generate Draft"}
      </button>
      <button
        type="button"
        class="bg-blue-600 hover:bg-blue-700 text-white rounded px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
        disabled={loading || publishing || !draft}
        on:click={publishDraft}
      >
        {publishing ? "Publishing..." : "Publish Draft"}
      </button>
      <button
        type="button"
        class="border border-stroke hover:bg-surface-alt rounded p-2 text-content-subtle hover:text-content"
        on:click={loadForecasts}
        aria-label="Refresh forecasts"
      >
        <svg
          class="w-5 h-5 animate-spin-hover"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3m0 0l3 3m-3-3v12"
          />
        </svg>
      </button>
    </div>
  </div>

  <!-- Status Notices -->
  {#if notice}
    <div
      class="rounded-lg border px-4 py-3 text-sm {notice.type === 'success'
        ? 'border-green-300 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950/40 dark:text-green-200'
        : 'border-red-300 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200'}"
      role={notice.type === "error" ? "alert" : "status"}
    >
      {notice.message}
    </div>
  {/if}

  {#if error}
    <div
      class="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800"
    >
      {error}
    </div>
  {:else if loading}
    <div
      class="rounded-lg border border-stroke bg-surface p-6 text-sm text-content-muted"
    >
      Loading forecasts...
    </div>
  {:else}
    <!-- Side-by-Side Comparison Panels -->
    <div class="grid gap-6 lg:grid-cols-2">
      <!-- Published Forecast Panel -->
      <div
        class="bg-surface border border-stroke rounded-xl p-5 shadow-sm space-y-4"
      >
        <div
          class="flex items-center justify-between border-b border-stroke pb-3"
        >
          <div class="flex items-center gap-2">
            <span
              class="px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300"
            >
              Published Forecast
            </span>
            <span class="text-xs text-content-faint">
              Updated: {published?.updated_at
                ? new Date(published.updated_at).toLocaleString()
                : "Never"}
            </span>
          </div>
        </div>

        {#if published}
          {#each chambersList as chamber}
            {@const chDetails = published.chambers?.[chamber]}
            <div
              class="border border-stroke/60 rounded-lg p-4 bg-surface-alt/40 space-y-3"
            >
              <div
                class="flex items-center justify-between border-b border-stroke/40 pb-2"
              >
                <h3
                  class="font-bold text-content uppercase tracking-wider text-xs"
                >
                  {chamber} Forecast
                </h3>
                {#if chDetails}
                  <span
                    class="text-xs font-semibold px-2 py-0.5 rounded bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
                  >
                    {chDetails.control_party} Projected ({chDetails.control_probability
                      ? (chDetails.control_probability * 100).toFixed(1)
                      : "50.0"}%)
                  </span>
                {/if}
              </div>

              {#if chDetails}
                <div class="space-y-2 text-sm text-content">
                  <div>
                    <span class="text-content-subtle font-semibold text-xs"
                      >Narrative:</span
                    >
                    <p class="mt-0.5 text-content-muted leading-relaxed">
                      {chDetails.narrative}
                    </p>
                  </div>
                  <div
                    class="grid grid-cols-2 gap-2 text-xs border-t border-stroke/40 pt-2 mt-2"
                  >
                    <div>
                      <span class="text-content-faint">Projected Seats:</span>
                      <span class="font-semibold block">
                        D: {chDetails.projected_seats?.Democratic ?? 0} | R: {chDetails
                          .projected_seats?.Republican ?? 0}
                      </span>
                    </div>
                    <div>
                      <span class="text-content-faint"
                        >Expected (Mean) Seats:</span
                      >
                      <span class="font-semibold block">
                        D: {chDetails.expected_seats?.Democratic ?? 0} | R: {chDetails
                          .expected_seats?.Republican ?? 0}
                      </span>
                    </div>
                  </div>
                  <div
                    class="text-xs bg-surface/60 border border-stroke/40 p-2 rounded space-y-1"
                  >
                    <div>
                      <span class="text-content-faint font-semibold"
                        >Bottom Line:</span
                      >
                      {chDetails.bottom_line || ""}
                    </div>
                    <div>
                      <span class="text-content-faint font-semibold"
                        >Why Favored:</span
                      >
                      {chDetails.why_party_favored || ""}
                    </div>
                    <div>
                      <span class="text-content-faint font-semibold"
                        >Opposing Path:</span
                      >
                      {chDetails.opposing_party_path || ""}
                    </div>
                    <div>
                      <span class="text-content-faint font-semibold"
                        >Key Uncertainty:</span
                      >
                      {chDetails.key_uncertainty || ""}
                    </div>
                  </div>
                </div>
              {:else}
                <p class="text-sm text-content-faint">
                  No details for {chamber}.
                </p>
              {/if}
            </div>
          {/each}
        {:else}
          <div
            class="py-12 text-center text-content-muted text-sm bg-surface-alt/20 border border-dashed border-stroke rounded-lg"
          >
            No published chamber forecast exists.
          </div>
        {/if}
      </div>

      <!-- Draft Forecast Panel -->
      <div
        class="bg-surface border border-stroke rounded-xl p-5 shadow-sm space-y-4"
      >
        <div
          class="flex items-center justify-between border-b border-stroke pb-3"
        >
          <div class="flex items-center gap-2">
            <span
              class="px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300"
            >
              Draft Forecast
            </span>
            <span class="text-xs text-content-faint">
              Generated: {draft?.updated_at
                ? new Date(draft.updated_at).toLocaleString()
                : "Never"}
            </span>
          </div>
        </div>

        {#if draft}
          {#each chambersList as chamber}
            {@const chDetails = draft.chambers?.[chamber]}
            <div
              class="border border-stroke/60 rounded-lg p-4 bg-surface-alt/40 space-y-3"
            >
              <div
                class="flex items-center justify-between border-b border-stroke/40 pb-2"
              >
                <h3
                  class="font-bold text-content uppercase tracking-wider text-xs"
                >
                  {chamber} Forecast
                </h3>
                {#if chDetails}
                  <span
                    class="text-xs font-semibold px-2 py-0.5 rounded bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
                  >
                    {chDetails.control_party} Projected ({chDetails.control_probability
                      ? (chDetails.control_probability * 100).toFixed(1)
                      : "50.0"}%)
                  </span>
                {/if}
              </div>

              {#if chDetails}
                <div class="space-y-2 text-sm text-content">
                  <div>
                    <span class="text-content-subtle font-semibold text-xs"
                      >Narrative:</span
                    >
                    <p class="mt-0.5 text-content-muted leading-relaxed">
                      {chDetails.narrative}
                    </p>
                  </div>
                  <div
                    class="grid grid-cols-2 gap-2 text-xs border-t border-stroke/40 pt-2 mt-2"
                  >
                    <div>
                      <span class="text-content-faint">Projected Seats:</span>
                      <span class="font-semibold block">
                        D: {chDetails.projected_seats?.Democratic ?? 0} | R: {chDetails
                          .projected_seats?.Republican ?? 0}
                      </span>
                    </div>
                    <div>
                      <span class="text-content-faint"
                        >Expected (Mean) Seats:</span
                      >
                      <span class="font-semibold block">
                        D: {chDetails.expected_seats?.Democratic ?? 0} | R: {chDetails
                          .expected_seats?.Republican ?? 0}
                      </span>
                    </div>
                  </div>
                  <div
                    class="text-xs bg-surface/60 border border-stroke/40 p-2 rounded space-y-1"
                  >
                    <div>
                      <span class="text-content-faint font-semibold"
                        >Bottom Line:</span
                      >
                      {chDetails.bottom_line || ""}
                    </div>
                    <div>
                      <span class="text-content-faint font-semibold"
                        >Why Favored:</span
                      >
                      {chDetails.why_party_favored || ""}
                    </div>
                    <div>
                      <span class="text-content-faint font-semibold"
                        >Opposing Path:</span
                      >
                      {chDetails.opposing_party_path || ""}
                    </div>
                    <div>
                      <span class="text-content-faint font-semibold"
                        >Key Uncertainty:</span
                      >
                      {chDetails.key_uncertainty || ""}
                    </div>
                  </div>
                </div>
              {:else}
                <p class="text-sm text-content-faint">
                  No details for {chamber}.
                </p>
              {/if}
            </div>
          {/each}
        {:else}
          <div
            class="py-12 text-center text-content-muted text-sm bg-surface-alt/20 border border-dashed border-stroke rounded-lg"
          >
            No draft chamber forecast exists. Click "Generate Draft" to create
            one.
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>
