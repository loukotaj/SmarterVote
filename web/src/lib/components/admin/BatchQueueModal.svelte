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
  let maxCandidates: number | null = null;
  let targetNoInfo = false;
  let showStepConfig = false;
  let stepToggles: Record<string, boolean> = Object.fromEntries(
    PIPELINE_STEPS.map((s) => [s.id, true])
  );
  let queuing = false;
  let error = "";

  function buildOptions(): RunOptions {
    const opts: RunOptions = {
      save_artifact: true,
      cheap_mode: cheapMode,
      enabled_steps: PIPELINE_STEPS.filter((s) => stepToggles[s.id]).map((s) => s.id),
    };
    if (maxCandidates !== null && maxCandidates > 0) opts.max_candidates = maxCandidates;
    if (targetNoInfo) opts.target_no_info = true;
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
      <div class="px-5 py-4 space-y-4 max-h-[60vh] overflow-y-auto">
        <!-- Race list -->
        <div>
          <span class="text-xs text-content-muted font-medium">Races to queue</span>
          <div class="mt-1 flex flex-wrap gap-1.5">
            {#each raceIds as id}
              <span class="px-2 py-0.5 text-xs font-mono bg-surface-alt rounded text-content">{id}</span>
            {/each}
          </div>
        </div>

        <!-- Options -->
        <div class="flex items-center gap-5">
          <label class="flex items-center gap-2 text-sm text-content-muted cursor-pointer">
            <input type="checkbox" bind:checked={cheapMode} class="rounded border-stroke text-blue-600 focus:ring-blue-500" />
            <span>Cheap Mode</span>
          </label>
          <label class="flex items-center gap-1.5 text-xs text-content-muted cursor-pointer">
            <input type="checkbox" bind:checked={targetNoInfo} class="rounded border-stroke text-blue-600 focus:ring-blue-500 h-3.5 w-3.5" />
            <span>Prioritize no-info</span>
          </label>
        </div>

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

        <!-- Step config -->
        <button
          type="button"
          on:click={() => (showStepConfig = !showStepConfig)}
          class="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"
        >
          <svg class="w-3 h-3 transition-transform {showStepConfig ? 'rotate-90' : ''}" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd" />
          </svg>
          Pipeline Steps
        </button>
        {#if showStepConfig}
          <div class="border-t border-stroke pt-2.5 space-y-2">
            <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {#each PIPELINE_STEPS as step}
                <label class="flex items-center gap-1.5 text-xs text-content-muted cursor-pointer select-none {step.id === 'discovery' ? 'opacity-60 cursor-not-allowed' : ''}">
                  <input
                    type="checkbox"
                    bind:checked={stepToggles[step.id]}
                    disabled={step.id === "discovery"}
                    class="rounded border-stroke text-blue-600 focus:ring-blue-500 h-3.5 w-3.5"
                  />
                  <span>{step.label}</span>
                </label>
              {/each}
            </div>
          </div>
        {/if}

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
