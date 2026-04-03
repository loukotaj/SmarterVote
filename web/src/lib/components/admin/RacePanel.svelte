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

  // Action states
  let running = false;
  let cancelling = false;
  let recovering = false;
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

  async function handleCancel() {
    const label = race.status === "running" ? "stop the current run" : "remove from queue";
    if (!confirm(`Are you sure you want to ${label} for "${race.race_id}"?`)) return;
    cancelling = true;
    error = "";
    try {
      await apiService.cancelRace(race.race_id);
      dispatch("updated");
      await loadRuns();
    } catch (e) {
      error = `Stop failed: ${e}`;
    } finally {
      cancelling = false;
    }
  }

  async function handleRecover() {
    recovering = true;
    error = "";
    try {
      await apiService.recheckRace(race.race_id);
      dispatch("updated");
      await loadRuns();
    } catch (e) {
      error = `Recover failed: ${e}`;
    } finally {
      recovering = false;
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

  async function handleExportDraft() {
    try {
      const data = await apiService.getRaceData(race.race_id, true);
      downloadAsJson(data, `${race.race_id}-draft.json`);
    } catch (e) {
      error = `Export draft failed: ${e}`;
    }
  }

  // True when a draft exists and is newer than the published version
  $: hasPendingUpdate =
    !!race.draft_updated_at &&
    !!race.published_at &&
    race.draft_updated_at > race.published_at;

  // True when a draft exists (regardless of publish state)
  $: hasDraft = !!race.draft_updated_at;

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
      <div class="flex items-center gap-2 px-5 py-3 border-b border-stroke bg-surface-alt flex-wrap">
        {#if race.status === "running" || race.status === "queued"}
          <button
            type="button"
            class="px-3 py-1.5 text-sm border border-red-300 dark:border-red-700 rounded-lg text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-40 flex items-center gap-1.5 font-medium"
            disabled={cancelling}
            on:click={handleCancel}
          >
            {#if race.status === "running"}
              <svg class="animate-spin h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            {/if}
            {cancelling ? "Stopping…" : race.status === "running" ? "Stop Run" : "Remove from Queue"}
          </button>
          <button
            type="button"
            class="px-3 py-1.5 text-sm border border-amber-300 dark:border-amber-700 rounded-lg text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-900/20 disabled:opacity-40 text-xs"
            disabled={recovering}
            title="Re-check status from storage — use if run completed but status is stuck"
            on:click={handleRecover}
          >
            {recovering ? "Checking…" : "Recover"}
          </button>
        {/if}
        {#if race.status === "draft" || (race.draft_updated_at && race.status !== "published")}
          <button
            type="button"
            class="px-3 py-1.5 text-sm border border-green-300 dark:border-green-700 rounded-lg text-green-700 dark:text-green-300 hover:bg-green-50 dark:hover:bg-green-900/20 disabled:opacity-40"
            disabled={publishing}
            on:click={handlePublish}
          >
            Publish{race.status !== "draft" ? " Draft" : ""}
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
        {#if race.status !== "running" && race.status !== "queued"}
          <button
            type="button"
            class="ml-auto text-xs text-blue-600 hover:underline font-medium"
            on:click={() => (activeTab = "output")}
          >
            Configure &amp; Run →
          </button>
        {/if}
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

            <!-- Pending-update banner -->
            {#if hasPendingUpdate}
              <div class="flex items-center gap-2.5 rounded-lg px-3 py-2.5 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 text-sm text-amber-800 dark:text-amber-200">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                </svg>
                <span class="flex-1">Draft is newer than published — unpublished changes exist.</span>
                <button
                  type="button"
                  class="shrink-0 text-xs font-semibold underline hover:no-underline"
                  on:click={handlePublish}
                  disabled={publishing}
                >Publish Now</button>
              </div>
            {/if}

            <!-- Status + quality hero row -->
            <div class="flex items-center gap-3">
              <span class="px-2.5 py-1 rounded-full text-xs font-semibold {statusBadge(race.status)} capitalize">{race.status}</span>
              {#if race.quality_score != null}
                <QualityBadge score={race.quality_score} />
              {/if}
              {#if race.freshness}
                <span class="text-xs text-content-faint capitalize ml-auto">{race.freshness} freshness</span>
              {/if}
            </div>

            <!-- Race facts grid -->
            <div class="grid grid-cols-2 gap-x-6 gap-y-3">
              <div>
                <span class="text-xs text-content-muted font-medium">Office</span>
                <p class="mt-0.5 text-sm text-content">{race.office ?? "—"}</p>
              </div>
              <div>
                <span class="text-xs text-content-muted font-medium">Jurisdiction</span>
                <p class="mt-0.5 text-sm text-content">{race.jurisdiction ?? "—"}</p>
              </div>
              <div>
                <span class="text-xs text-content-muted font-medium">Election Date</span>
                <p class="mt-0.5 text-sm text-content">{race.election_date ?? "—"}</p>
              </div>
              <div>
                <span class="text-xs text-content-muted font-medium">Candidates</span>
                <p class="mt-0.5 text-sm text-content">{race.candidate_count || "—"}</p>
              </div>
            </div>

            <!-- Versions section -->
            <div class="border-t border-stroke pt-3 space-y-2">
              <span class="text-xs font-semibold text-content-muted uppercase tracking-wide">Versions</span>

              {#if race.published_at}
                <div class="flex items-center justify-between rounded-md px-3 py-2 bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800">
                  <div>
                    <span class="text-xs font-medium text-green-700 dark:text-green-300">Published</span>
                    <p class="text-xs text-content-faint">{formatDate(race.published_at)}</p>
                  </div>
                  <a
                    href="/races/{race.race_id}"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium"
                  >View page →</a>
                </div>
              {/if}

              {#if hasDraft}
                <div class="flex items-center justify-between rounded-md px-3 py-2 {hasPendingUpdate ? 'bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800' : 'bg-surface-alt border border-stroke'}">
                  <div>
                    <span class="text-xs font-medium {hasPendingUpdate ? 'text-amber-700 dark:text-amber-300' : 'text-content-muted'}">Draft</span>
                    <p class="text-xs text-content-faint">{formatDate(race.draft_updated_at)}</p>
                  </div>
                  <button
                    type="button"
                    class="text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium"
                    on:click={handleExportDraft}
                  >Export draft →</button>
                </div>
              {/if}

              {#if !race.published_at && !hasDraft}
                <p class="text-xs text-content-faint py-1">No versions yet — run the pipeline to generate a draft.</p>
              {/if}
            </div>

            <!-- Pipeline activity -->
            <div class="border-t border-stroke pt-3 grid grid-cols-2 gap-x-6 gap-y-3">
              <div>
                <span class="text-xs text-content-muted font-medium">Last Run</span>
                <p class="mt-0.5 text-sm text-content">
                  {formatDate(race.last_run_at)}
                  {#if race.last_run_status}
                    <span class="ml-1 text-xs px-1.5 py-0.5 rounded {statusBadge(race.last_run_status)}">{race.last_run_status}</span>
                  {/if}
                </p>
              </div>
              <div>
                <span class="text-xs text-content-muted font-medium">Total Runs</span>
                <p class="mt-0.5 text-sm text-content">{race.total_runs}</p>
              </div>
            </div>

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
          <div class="space-y-5 pb-4">

            <!-- Research model -->
            <div>
              <label for="panelResearchModel" class="block text-sm font-semibold text-content mb-1.5">Research Model</label>
              <select
                id="panelResearchModel"
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
              <label class="flex items-center gap-1.5 text-xs text-content-muted cursor-pointer">
                <input type="checkbox" bind:checked={targetNoInfo} class="rounded border-stroke text-blue-600 focus:ring-blue-500 h-3.5 w-3.5" />
                <span>Prioritize no-info candidates</span>
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
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
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

            <!-- Run Button -->
            <div class="pt-3 border-t border-stroke">
              <button
                type="button"
                class="btn-primary w-full py-2.5 text-sm rounded-lg font-semibold disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                disabled={running || race.status === "running" || race.status === "queued"}
                on:click={handleRun}
              >
                {#if running}
                  <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                    <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Queuing…
                {:else if race.status === "running"}
                  Running — use Stop above to cancel
                {:else if race.status === "queued"}
                  Already Queued
                {:else}
                  Run Pipeline
                {/if}
              </button>
            </div>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>
