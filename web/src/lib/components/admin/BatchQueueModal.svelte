<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import { PipelineApiService } from "$lib/services/pipelineApiService";
  import type { RunOptions } from "$lib/types";
  import { PIPELINE_STEPS } from "$lib/types";

  export let open = false;
  export let raceIds: string[] = [];

  const dispatch = createEventDispatcher<{
    close: void;
    queued: { added: number; errors: string[] };
  }>();

  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";
  const apiService = new PipelineApiService(API_BASE);

  let cheapMode = true;
  let forceFresh = false;
  let maxCandidates: number | null = null;
  let targetNoInfo = false;
  let stepToggles: Record<string, boolean> = Object.fromEntries(
    PIPELINE_STEPS.map((s) => [s.id, true])
  );
  let researchModel = "";

  type ReviewerKey = "claude" | "gemini" | "grok";
  const REVIEWER_DEFS: { key: ReviewerKey; name: string; options: { value: string; label: string }[] }[] = [
    { key: "claude", name: "Claude", options: [
      { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
      { value: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" },
    ]},
    { key: "gemini", name: "Gemini", options: [
      { value: "gemini-3-flash-preview", label: "Gemini 3 Flash" },
      { value: "gemini-3.1-flash-lite-preview", label: "Gemini 3.1 Flash Lite" },
    ]},
    { key: "grok", name: "Grok", options: [
      { value: "grok-3", label: "Grok 3" },
      { value: "grok-3-mini", label: "Grok 3 mini" },
    ]},
  ];
  const RESEARCH_MODELS = [
    { value: "", label: "Auto (cheap mode selects)" },
    { value: "gpt-5.4", label: "GPT-5.4 — best quality" },
    { value: "gpt-5.4-mini", label: "GPT-5.4 mini — fast & smart" },
    { value: "gpt-5-nano", label: "GPT-5 nano — fastest & cheapest" },
  ];
  let reviewerEnabled: Record<ReviewerKey, boolean> = { claude: false, gemini: false, grok: false };
  let reviewerModels: Record<ReviewerKey, string> = {
    claude: "claude-sonnet-4-6",
    gemini: "gemini-3-flash-preview",
    grok: "grok-3",
  };
  let queuing = false;
  let error = "";

  function buildOptions(): RunOptions {
    const opts: RunOptions = {
      save_artifact: true,
      cheap_mode: cheapMode,
      force_fresh: forceFresh,
      enabled_steps: PIPELINE_STEPS.filter((s) => stepToggles[s.id]).map((s) => s.id),
    };
    if (researchModel) opts.research_model = researchModel;
    if (maxCandidates !== null && maxCandidates > 0) opts.max_candidates = maxCandidates;
    if (targetNoInfo) opts.target_no_info = true;
    const anyReviewer = REVIEWER_DEFS.some((r) => reviewerEnabled[r.key]);
    opts.enable_review = anyReviewer;
    if (reviewerEnabled.claude) opts.claude_model = reviewerModels.claude;
    if (reviewerEnabled.gemini) opts.gemini_model = reviewerModels.gemini;
    if (reviewerEnabled.grok) opts.grok_model = reviewerModels.grok;
    return opts;
  }

  async function handleQueue() {
    queuing = true;
    error = "";
    try {
      const result = await apiService.queueRaces(raceIds, buildOptions());
      dispatch("queued", {
        added: result.added.length,
        errors: result.errors.map((e) => `${e.race_id}: ${e.error}`),
      });
    } catch (e) {
      error = String(e);
    } finally {
      queuing = false;
    }
  }

  function handleClose() {
    dispatch("close");
  }
</script>

{#if open}
  <!-- Backdrop -->
  <div
    class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
    on:click={handleClose}
    on:keydown={(e) => e.key === "Escape" && handleClose()}
    role="button"
    tabindex="-1"
  >
    <!-- Modal -->
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
    <div
      class="bg-surface rounded-xl shadow-xl w-full max-w-lg mx-4 overflow-hidden"
      on:click|stopPropagation
      role="dialog"
    >
      <!-- Header -->
      <div class="flex items-center justify-between px-5 py-4 border-b border-stroke">
        <h2 class="text-lg font-bold text-content">Queue {raceIds.length} Races</h2>
        <button type="button" on:click={handleClose} class="p-1 rounded hover:bg-surface-alt text-content-muted">
          <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>

      <!-- Body -->
      <div class="px-5 py-4 space-y-5 max-h-[70vh] overflow-y-auto">
        <!-- Race list -->
        <div>
          <span class="text-xs text-content-muted font-medium">Races to queue</span>
          <div class="mt-1 flex flex-wrap gap-1.5">
            {#each raceIds as id}
              <span class="px-2 py-0.5 text-xs font-mono bg-surface-alt rounded text-content">{id}</span>
            {/each}
          </div>
        </div>

        <!-- Research model -->
        <div>
          <label for="batchResearchModel" class="block text-sm font-semibold text-content mb-1.5">Research Model</label>
          <select
            id="batchResearchModel"
            bind:value={researchModel}
            class="w-full px-3 py-2 border border-stroke rounded-lg text-sm bg-surface text-content focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          >
            {#each RESEARCH_MODELS as m}
              <option value={m.value}>{m.label}</option>
            {/each}
          </select>
        </div>

        <!-- Mode + limits -->
        <div class="flex flex-wrap items-center gap-x-6 gap-y-3">
          <label class="flex items-center gap-2 text-sm text-content-muted cursor-pointer">
            <input type="checkbox" bind:checked={cheapMode} class="rounded border-stroke text-blue-600 focus:ring-blue-500" />
            <span>Cheap Mode</span>
          </label>
          <label class="flex items-center gap-2 text-sm cursor-pointer" title="Ignore existing data and research from scratch">
            <input type="checkbox" bind:checked={forceFresh} class="rounded border-stroke text-orange-500 focus:ring-orange-500" />
            <span class="text-orange-600 dark:text-orange-400 font-medium">Fresh Run</span>
          </label>
          <div class="flex items-center gap-2">
            <label for="batchMax" class="text-xs text-content-muted">Max candidates</label>
            <input
              id="batchMax"
              type="number"
              min="1"
              placeholder="All"
              value={maxCandidates ?? ""}
              on:input={(e) => { const v = parseInt(e.currentTarget.value); maxCandidates = isNaN(v) ? null : v; }}
              class="w-16 px-2 py-1 border border-stroke rounded text-xs bg-surface text-content focus:outline-none focus:border-blue-500"
            />
          </div>
          <label class="flex items-center gap-1.5 text-xs text-content-muted cursor-pointer">
            <input type="checkbox" bind:checked={targetNoInfo} class="rounded border-stroke text-blue-600 focus:ring-blue-500 h-3.5 w-3.5" />
            <span>Prioritize no-info</span>
          </label>
        </div>

        <!-- Pipeline Steps -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-semibold text-content">Pipeline Steps</span>
            <div class="flex gap-3 text-xs text-blue-600">
              <button type="button" on:click={() => { PIPELINE_STEPS.forEach((s) => { stepToggles[s.id] = true; }); stepToggles = stepToggles; }}>All on</button>
              <button type="button" on:click={() => { PIPELINE_STEPS.forEach((s) => { stepToggles[s.id] = s.id === "discovery"; }); stepToggles = stepToggles; }}>Discovery only</button>
            </div>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {#each PIPELINE_STEPS as step}
              <label
                class="flex items-center gap-2 px-2.5 py-2 rounded-lg border text-xs font-medium cursor-pointer select-none transition-colors
                  {stepToggles[step.id]
                    ? 'border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-700 dark:bg-blue-900/20 dark:text-blue-300'
                    : 'border-stroke bg-surface text-content-muted hover:bg-surface-alt'}
                  {step.id === 'discovery' ? 'opacity-60 !cursor-not-allowed' : ''}"
              >
                <input type="checkbox" bind:checked={stepToggles[step.id]} disabled={step.id === "discovery"} class="sr-only" />
                <span class="w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0 transition-colors {stepToggles[step.id] ? 'border-blue-500 bg-blue-500' : 'border-stroke'}">
                  {#if stepToggles[step.id]}
                    <svg class="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 20 20">
                      <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                    </svg>
                  {/if}
                </span>
                {step.label}
              </label>
            {/each}
          </div>
        </div>

        <!-- AI Reviewers -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-semibold text-content">AI Reviewers</span>
            <span class="text-xs text-content-faint">Each enabled model independently reviews the research</span>
          </div>
          <div class="space-y-2.5">
            {#each REVIEWER_DEFS as reviewer}
              <div class="flex items-center gap-3">
                <label class="flex items-center gap-2 text-sm text-content-muted cursor-pointer w-20 shrink-0">
                  <input type="checkbox" bind:checked={reviewerEnabled[reviewer.key]} class="rounded border-stroke text-blue-600 focus:ring-blue-500" />
                  {reviewer.name}
                </label>
                <select
                  bind:value={reviewerModels[reviewer.key]}
                  disabled={!reviewerEnabled[reviewer.key]}
                  class="flex-1 px-2 py-1.5 border border-stroke rounded text-xs bg-surface text-content focus:outline-none focus:border-blue-500 disabled:opacity-40"
                >
                  {#each reviewer.options as opt}
                    <option value={opt.value}>{opt.label}</option>
                  {/each}
                </select>
              </div>
            {/each}
          </div>
        </div>

        {#if error}
          <div class="text-sm text-red-600">{error}</div>
        {/if}
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-end gap-2 px-5 py-3 border-t border-stroke bg-surface-alt">
        <button
          type="button"
          class="px-4 py-2 text-sm border border-stroke rounded-lg text-content hover:bg-surface-alt"
          on:click={handleClose}
        >
          Cancel
        </button>
        <button
          type="button"
          class="btn-primary px-4 py-2 text-sm rounded-lg disabled:opacity-40"
          disabled={queuing || raceIds.length === 0}
          on:click={handleQueue}
        >
          {queuing ? "Queuing…" : `Queue ${raceIds.length} Race${raceIds.length !== 1 ? "s" : ""}`}
        </button>
      </div>
    </div>
  </div>
{/if}
