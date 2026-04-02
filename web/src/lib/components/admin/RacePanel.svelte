<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte";
  import { PipelineApiService } from "$lib/services/pipelineApiService";
  import QualityBadge from "./QualityBadge.svelte";
  import type { RaceRecord, RunInfo, RunOptions } from "$lib/types";
  import { PIPELINE_STEPS } from "$lib/types";
  import { downloadAsJson } from "$lib/utils/pipelineUtils";

  export let race: RaceRecord;
  export let open = false;

  const dispatch = createEventDispatcher<{
    close: void;
    runStarted: { race_id: string; run_id: string };
    updated: void;
    viewRun: string;
  }>();

  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";
  const apiService = new PipelineApiService(API_BASE);

  type Tab = "overview" | "runs" | "output";
  const panelTabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "runs", label: "Runs" },
    { id: "output", label: "Pipeline Options" },
  ];
  let activeTab: Tab = "overview";

  // Runs
  let runs: RunInfo[] = [];
  let runsLoading = false;
  let runsError = "";

  // Pipeline options
  let cheapMode = true;
  let showStepConfig = false;
  let maxCandidates: number | null = null;
  let targetNoInfo = false;
  let stepToggles: Record<string, boolean> = Object.fromEntries(
    PIPELINE_STEPS.map((s) => [s.id, true])
  );

  // Action states
  let running = false;
  let publishing = false;
  let error = "";

  $: if (open && race) {
    activeTab = "overview";
    loadRuns();
  }

  async function loadRuns() {
    runsLoading = true;
    runsError = "";
    try {
      runs = await apiService.listRaceRuns(race.race_id, 20);
    } catch (e) {
      runsError = String(e);
    } finally {
      runsLoading = false;
    }
  }

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

  async function handleRun() {
    running = true;
    error = "";
    try {
      const result = await apiService.runRace(race.race_id, buildOptions());
      dispatch("runStarted", { race_id: race.race_id, run_id: result.run_id });
      await loadRuns();
    } catch (e) {
      error = `Run failed: ${e}`;
    } finally {
      running = false;
    }
  }

  async function handlePublish() {
    publishing = true;
    error = "";
    try {
      await apiService.publishRace(race.race_id);
      dispatch("updated");
    } catch (e) {
      error = `Publish failed: ${e}`;
    } finally {
      publishing = false;
    }
  }

  async function handleUnpublish() {
    if (!confirm(`Unpublish "${race.race_id}"?`)) return;
    publishing = true;
    error = "";
    try {
      await apiService.unpublishRaceRecord(race.race_id);
      dispatch("updated");
    } catch (e) {
      error = `Unpublish failed: ${e}`;
    } finally {
      publishing = false;
    }
  }

  async function handleExport() {
    try {
      const data = await apiService.getRaceData(race.race_id);
      downloadAsJson(data, `${race.race_id}.json`);
    } catch (e) {
      error = `Export failed: ${e}`;
    }
  }

  function handleClose() {
    dispatch("close");
  }

  function handleViewRun(runId: string) {
    dispatch("viewRun", runId);
  }

  function formatDate(s?: string): string {
    if (!s) return "—";
    return new Date(s).toLocaleString(undefined, {
      month: "short", day: "numeric", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  }

  function statusBadge(s: string): string {
    switch (s) {
      case "completed": return "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300";
      case "failed": return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300";
      case "running": return "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300";
      case "cancelled": return "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300";
      default: return "bg-surface-alt text-content-subtle";
    }
  }

  function formatDuration(ms?: number): string {
    if (!ms) return "—";
    if (ms < 60000) return `${Math.round(ms / 1000)}s`;
    return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
  }
</script>

<!-- Backdrop -->
{#if open}
  <div
    class="fixed inset-0 z-40 bg-black/30 transition-opacity"
    on:click={handleClose}
    on:keydown={(e) => e.key === "Escape" && handleClose()}
    role="button"
    tabindex="-1"
  />
{/if}

<!-- Panel -->
<div
  class="fixed top-0 right-0 z-50 h-full w-full max-w-2xl bg-surface border-l border-stroke shadow-xl transform transition-transform duration-200 {open ? 'translate-x-0' : 'translate-x-full'}"
>
  {#if open && race}
    <div class="flex flex-col h-full">
      <!-- Header -->
      <div class="flex items-center justify-between px-5 py-4 border-b border-stroke">
        <div class="min-w-0 flex-1">
          <h2 class="text-lg font-bold text-content truncate">{race.title ?? race.race_id}</h2>
          <p class="text-sm text-content-muted font-mono">{race.race_id}</p>
        </div>
        <button
          type="button"
          on:click={handleClose}
          class="ml-3 p-1.5 rounded-lg hover:bg-surface-alt text-content-muted"
        >
          <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>

      <!-- Action Bar -->
      <div class="flex items-center gap-2 px-5 py-3 border-b border-stroke bg-surface-alt">
        <button
          type="button"
          class="btn-primary px-3 py-1.5 text-sm rounded-lg disabled:opacity-40"
          disabled={running || race.status === "running" || race.status === "queued"}
          on:click={handleRun}
        >
          {running ? "Starting…" : race.status === "running" ? "Running…" : race.status === "queued" ? "Queued" : "Run Pipeline"}
        </button>
        {#if race.status === "draft"}
          <button
            type="button"
            class="px-3 py-1.5 text-sm border border-green-300 dark:border-green-700 rounded-lg text-green-700 dark:text-green-300 hover:bg-green-50 dark:hover:bg-green-900/20 disabled:opacity-40"
            disabled={publishing}
            on:click={handlePublish}
          >
            Publish
          </button>
        {/if}
        {#if race.status === "published"}
          <button
            type="button"
            class="px-3 py-1.5 text-sm border border-amber-300 dark:border-amber-700 rounded-lg text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-900/20 disabled:opacity-40"
            disabled={publishing}
            on:click={handleUnpublish}
          >
            Unpublish
          </button>
        {/if}
        <button
          type="button"
          class="px-3 py-1.5 text-sm border border-stroke rounded-lg text-content-muted hover:bg-surface-alt"
          on:click={handleExport}
        >
          Export
        </button>
        <a
          href="/races/{race.race_id}"
          target="_blank"
          class="px-3 py-1.5 text-sm border border-stroke rounded-lg text-content-muted hover:bg-surface-alt"
        >
          View Page
        </a>
      </div>

      {#if error}
        <div class="px-5 py-2 text-sm text-red-600 bg-red-50 dark:bg-red-900/20">{error}</div>
      {/if}

      <!-- Tabs -->
      <div class="flex border-b border-stroke px-5">
        {#each panelTabs as tab}
          <button
            type="button"
            class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors {activeTab === tab.id
              ? 'border-blue-600 text-blue-700 dark:text-blue-300'
              : 'border-transparent text-content-muted hover:text-content'}"
            on:click={() => (activeTab = tab.id)}
          >
            {tab.id === "runs" ? `Runs (${runs.length})` : tab.label}
          </button>
        {/each}
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto px-5 py-4">
        {#if activeTab === "overview"}
          <div class="space-y-4">
            <div class="grid grid-cols-2 gap-4">
              <div>
                <span class="text-xs text-content-muted font-medium">Status</span>
                <p class="mt-1">
                  <span class="px-2 py-0.5 rounded-full text-xs font-medium {statusBadge(race.status)}">{race.status}</span>
                </p>
              </div>
              <div>
                <span class="text-xs text-content-muted font-medium">Quality</span>
                <p class="mt-1">
                  {#if race.quality_score != null}
                    <QualityBadge score={race.quality_score} />
                  {:else}
                    <span class="text-content-faint">—</span>
                  {/if}
                </p>
              </div>
              <div>
                <span class="text-xs text-content-muted font-medium">Office</span>
                <p class="mt-1 text-sm text-content">{race.office ?? "—"}</p>
              </div>
              <div>
                <span class="text-xs text-content-muted font-medium">Jurisdiction</span>
                <p class="mt-1 text-sm text-content">{race.jurisdiction ?? "—"}</p>
              </div>
              <div>
                <span class="text-xs text-content-muted font-medium">Election Date</span>
                <p class="mt-1 text-sm text-content">{race.election_date ?? "—"}</p>
              </div>
              <div>
                <span class="text-xs text-content-muted font-medium">Candidates</span>
                <p class="mt-1 text-sm text-content">{race.candidate_count || "—"}</p>
              </div>
              <div>
                <span class="text-xs text-content-muted font-medium">Published At</span>
                <p class="mt-1 text-sm text-content">{formatDate(race.published_at)}</p>
              </div>
              <div>
                <span class="text-xs text-content-muted font-medium">Draft Updated</span>
                <p class="mt-1 text-sm text-content">{formatDate(race.draft_updated_at)}</p>
              </div>
              <div>
                <span class="text-xs text-content-muted font-medium">Last Run</span>
                <p class="mt-1 text-sm text-content">{formatDate(race.last_run_at)}
                  {#if race.last_run_status}
                    <span class="ml-1 text-xs px-1.5 py-0.5 rounded {statusBadge(race.last_run_status)}">{race.last_run_status}</span>
                  {/if}
                </p>
              </div>
              <div>
                <span class="text-xs text-content-muted font-medium">Total Runs</span>
                <p class="mt-1 text-sm text-content">{race.total_runs}</p>
              </div>
            </div>
            {#if race.freshness}
              <div>
                <span class="text-xs text-content-muted font-medium">Freshness</span>
                <p class="mt-1 text-sm text-content capitalize">{race.freshness}</p>
              </div>
            {/if}
          </div>

        {:else if activeTab === "runs"}
          <div class="space-y-2">
            {#if runsLoading}
              <div class="py-8 text-center text-content-faint text-sm">Loading runs…</div>
            {:else if runsError}
              <div class="py-4 text-sm text-red-600">{runsError}</div>
            {:else if runs.length === 0}
              <div class="py-8 text-center text-content-faint text-sm">No runs yet</div>
            {:else}
              {#each runs as run (run.run_id)}
                <button
                  type="button"
                  class="w-full text-left card p-3 hover:bg-surface-alt transition-colors"
                  on:click={() => handleViewRun(run.run_id)}
                >
                  <div class="flex items-center justify-between">
                    <span class="text-sm font-mono text-content">{run.run_id.substring(0, 12)}…</span>
                    <span class="text-xs px-2 py-0.5 rounded-full {statusBadge(run.status)}">{run.status}</span>
                  </div>
                  <div class="flex items-center gap-3 mt-1 text-xs text-content-faint">
                    <span>{formatDate(run.started_at)}</span>
                    {#if run.duration_ms}
                      <span>· {formatDuration(run.duration_ms)}</span>
                    {/if}
                    {#if run.options?.research_model}
                      <span class="ml-auto font-mono">{run.options.research_model}</span>
                    {/if}
                  </div>
                  {#if run.error}
                    <p class="text-xs text-red-500 mt-1 truncate">{run.error}</p>
                  {/if}
                </button>
              {/each}
            {/if}
          </div>

        {:else if activeTab === "output"}
          <div class="space-y-4">
            <div class="flex items-center gap-5">
              <label class="flex items-center gap-2 text-sm text-content-muted cursor-pointer">
                <input type="checkbox" bind:checked={cheapMode} class="rounded border-stroke text-blue-600 focus:ring-blue-500" />
                <span>Cheap Mode</span>
              </label>
              <label class="flex items-center gap-1.5 text-xs text-content-muted cursor-pointer">
                <input type="checkbox" bind:checked={targetNoInfo} class="rounded border-stroke text-blue-600 focus:ring-blue-500 h-3.5 w-3.5" />
                <span>Prioritize no-info candidates</span>
              </label>
            </div>
            <div class="flex items-center gap-2">
              <label for="panelMaxCandidates" class="text-xs text-content-muted whitespace-nowrap">Max candidates</label>
              <input
                id="panelMaxCandidates"
                type="number"
                min="1"
                placeholder="All"
                value={maxCandidates ?? ""}
                on:input={(e) => { const v = parseInt(e.currentTarget.value); maxCandidates = isNaN(v) ? null : v; }}
                class="w-16 px-2 py-1 border border-stroke rounded text-xs bg-surface text-content focus:outline-none focus:border-blue-500"
              />
            </div>

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
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
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
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>
