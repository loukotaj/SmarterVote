<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher } from "svelte";
  import { PipelineApiService } from "$lib/services/pipelineApiService";
  import { formatDuration, getStatusClass, safeJsonStringify, downloadAsJson } from "$lib/utils/pipelineUtils";
  import type { RunInfo, RunStep, LogEntry } from "$lib/types";

  export let runId: string;
  export let isLive = false;
  export let liveLogs: LogEntry[] = [];
  export let liveProgress = 0;
  export let liveProgressMessage = "";
  export let liveElapsed = 0;

  const dispatch = createEventDispatcher<{ back: void }>();
  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";
  const apiService = new PipelineApiService(API_BASE);

  let run: RunInfo | null = null;
  let loading = true;
  let error = "";
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let showRawJson = false;
  type SectionId = "steps" | "logs" | "output";
  let activeSection: SectionId = "steps";
  let artifactData: any = null;
  let artifactLoading = false;
  type LogLevel = "all" | "info" | "warning" | "error";
  const LOG_LEVELS: LogLevel[] = ["all", "info", "warning", "error"];
  let logFilter: LogLevel = "all";

  $: raceId = (run?.payload?.race_id as string) ?? runId;
  $: isRunning = run?.status === "running" || run?.status === "pending";
  $: runLogs = isLive ? liveLogs : (run?.logs ?? []);
  $: filteredLogs = logFilter === "all" ? runLogs : runLogs.filter((l) => l.level === logFilter);
  $: steps = run?.steps ?? [];
  $: sections = [
    { id: "steps" as SectionId, label: `Steps (${steps.length})` },
    { id: "logs" as SectionId, label: `Logs (${runLogs.length})` },
    { id: "output" as SectionId, label: "Output" },
  ];
  $: progress = isLive && isRunning ? liveProgress : computeProgress(steps);
  $: progressMsg = isLive && isRunning ? liveProgressMessage : lastStepMessage(steps);
  $: elapsed = isLive && isRunning ? liveElapsed : (run?.duration_ms ? Math.floor(run.duration_ms / 1000) : 0);

  function computeProgress(steps: RunStep[]): number {
    if (!steps.length) return 0;
    const done = steps.filter((s) => s.status === "completed").length;
    return Math.round((done / steps.length) * 100);
  }

  function lastStepMessage(steps: RunStep[]): string {
    const running = steps.find((s) => s.status === "running");
    if (running) return `Running: ${running.name}`;
    const last = [...steps].reverse().find((s) => s.status === "completed");
    if (last) return `Completed: ${last.name}`;
    return "";
  }

  function stepIcon(status: string): string {
    switch (status) {
      case "completed": return "✓";
      case "running": return "●";
      case "failed": return "✗";
      default: return "○";
    }
  }

  function stepColor(status: string): string {
    switch (status) {
      case "completed": return "text-green-600";
      case "running": return "text-blue-600";
      case "failed": return "text-red-600";
      default: return "text-gray-400";
    }
  }

  function statusBadge(status: string): string {
    switch (status) {
      case "completed": return "bg-green-100 text-green-800";
      case "running": return "bg-blue-100 text-blue-800";
      case "failed": return "bg-red-100 text-red-800";
      case "cancelled": return "bg-yellow-100 text-yellow-800";
      case "pending": return "bg-gray-100 text-gray-600";
      default: return "bg-gray-100 text-gray-600";
    }
  }

  function formatTimestamp(iso?: string): string {
    if (!iso) return "—";
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  }

  function logLevelClass(level: string): string {
    switch (level) {
      case "error": return "text-red-600";
      case "warning": return "text-yellow-600";
      case "debug": return "text-gray-400";
      default: return "text-gray-700";
    }
  }

  function breakdownTokens(counts: unknown): number {
    const c = counts as { prompt_tokens?: number; completion_tokens?: number };
    return (c?.prompt_tokens ?? 0) + (c?.completion_tokens ?? 0);
  }

  async function loadRun() {
    try {
      error = "";
      run = await apiService.getRunDetails(runId);
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  async function loadArtifact() {
    if (!run?.artifact_id) return;
    artifactLoading = true;
    try {
      artifactData = await apiService.getArtifact(run.artifact_id);
    } catch (e) {
      artifactData = { error: String(e) };
    } finally {
      artifactLoading = false;
    }
  }

  onMount(async () => {
    await loadRun();
    if (isRunning) {
      pollTimer = setInterval(loadRun, 3000);
    }
  });

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  // If the run finishes, stop polling and load artifact
  $: if (run && !isRunning && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
</script>

<div class="space-y-4">
  <!-- Back button + header -->
  <div class="flex items-center gap-3">
    <button
      type="button"
      class="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-gray-700"
      on:click={() => dispatch("back")}
      title="Back to runs"
    >
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
      </svg>
    </button>
    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-3">
        <h2 class="text-lg font-bold text-gray-900 truncate">{raceId}</h2>
        {#if run}
          <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold {statusBadge(run.status)}">
            {run.status}
          </span>
        {/if}
        {#if isRunning}
          <span class="flex items-center gap-1 text-xs text-blue-600">
            <svg class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            Live
          </span>
        {/if}
      </div>
      <div class="flex items-center gap-4 mt-0.5 text-xs text-gray-500">
        <span>Run {runId.substring(0, 8)}</span>
        {#if run}
          <span>Started {formatTimestamp(run.started_at)}</span>
          {#if run.completed_at}
            <span>Finished {formatTimestamp(run.completed_at)}</span>
          {/if}
          {#if run.options?.research_model}
            <span class="font-mono">{run.options.research_model}</span>
          {/if}          {#if run.options?.note}
            <span class="italic text-gray-400">"{run.options.note}"</span>
          {/if}        {/if}
      </div>
    </div>
  </div>

  {#if loading}
    <div class="card p-8 text-center">
      <svg class="animate-spin h-6 w-6 mx-auto text-blue-500 mb-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
      </svg>
      <span class="text-sm text-gray-500">Loading run details…</span>
    </div>
  {:else if error}
    <div class="card p-4 text-sm text-red-600">{error}</div>
  {:else if run}
    <!-- Progress bar -->
    <div class="card p-4">
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm text-gray-700 font-medium">{progressMsg || "Waiting…"}</span>
        <div class="flex items-center gap-3 text-sm text-gray-500">
          <span>{formatDuration(elapsed)}</span>
          <span class="font-semibold">{progress}%</span>
        </div>
      </div>
      <div class="w-full bg-gray-200 rounded-full h-2.5">
        <div
          class="h-2.5 rounded-full transition-all duration-700 ease-out {run.status === 'failed' ? 'bg-red-500' : run.status === 'completed' ? 'bg-green-500' : 'bg-blue-600'}"
          style="width: {progress}%"
        />
      </div>
      {#if run.error}
        <p class="mt-2 text-sm text-red-600">{run.error}</p>
      {/if}
    </div>

    <!-- Section tabs -->
    <div class="flex gap-1 border-b border-gray-200">
      {#each sections as sec}
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium transition-colors {activeSection === sec.id ? 'border-b-2 border-blue-600 text-blue-700' : 'text-gray-500 hover:text-gray-700'}"
          on:click={() => (activeSection = sec.id)}
        >
          {sec.label}
        </button>
      {/each}
    </div>

    <!-- Steps section -->
    {#if activeSection === "steps"}
      <div class="card p-0 divide-y divide-gray-100">
        {#each steps as step, i}
          <div class="px-4 py-3 flex items-center gap-3">
            <span class="text-lg font-bold {stepColor(step.status)} w-6 text-center">{stepIcon(step.status)}</span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-sm font-medium text-gray-900">{step.name}</span>
                {#if step.status === "running"}
                  <svg class="animate-spin h-3.5 w-3.5 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                    <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                {/if}
              </div>
              <div class="flex items-center gap-3 text-xs text-gray-400 mt-0.5">
                {#if step.started_at}
                  <span>{formatTimestamp(step.started_at)}</span>
                {/if}
                {#if step.duration_ms}
                  <span>{formatDuration(Math.floor(step.duration_ms / 1000))}</span>
                {/if}
                {#if step.artifact_id}
                  <span class="font-mono text-blue-500">{step.artifact_id.substring(0, 12)}…</span>
                {/if}
              </div>
              {#if step.error}
                <p class="text-xs text-red-500 mt-1">{step.error}</p>
              {/if}
            </div>
            <span class="text-xs text-gray-400 shrink-0">{i + 1}/{steps.length}</span>
          </div>
        {:else}
          <div class="p-6 text-center text-gray-400 text-sm">No step data recorded</div>
        {/each}
      </div>
    {/if}

    <!-- Logs section -->
    {#if activeSection === "logs"}
      <div class="card p-0">
        <div class="px-4 py-2 border-b border-gray-100 flex items-center gap-2">
          <span class="text-xs font-medium text-gray-500">Filter:</span>
          {#each LOG_LEVELS as level}
            <button
              type="button"
              class="px-2 py-0.5 rounded text-xs font-medium transition-colors {logFilter === level ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:bg-gray-100'}"
              on:click={() => (logFilter = level)}
            >{level}</button>
          {/each}
          <span class="ml-auto text-xs text-gray-400">{filteredLogs.length} entries</span>
        </div>
        <div class="max-h-96 overflow-y-auto font-mono text-xs p-3 space-y-0.5 bg-gray-50">
          {#each filteredLogs as log}
            <div class="flex gap-2 leading-5">
              <span class="text-gray-400 shrink-0 select-none">{log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : ""}</span>
              <span class="shrink-0 w-14 text-right font-semibold uppercase {logLevelClass(log.level)}">{log.level}</span>
              <span class="{logLevelClass(log.level)} break-all">{log.message}</span>
            </div>
          {:else}
            <div class="text-center text-gray-400 py-6">No logs available</div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Output section -->
    {#if activeSection === "output"}
      <div class="card p-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold text-gray-700">
            {#if run.artifact_id}
              Artifact: <span class="font-mono text-gray-500">{run.artifact_id}</span>
            {:else}
              Run Output
            {/if}
          </h3>
          <div class="flex items-center gap-2">
            {#if run.artifact_id && !artifactData}
              <button
                type="button"
                class="px-3 py-1 text-xs border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40"
                disabled={artifactLoading}
                on:click={loadArtifact}
              >
                {artifactLoading ? "Loading…" : "Load Artifact"}
              </button>
            {/if}
            {#if artifactData}
              <button
                type="button"
                class="px-3 py-1 text-xs border border-gray-300 rounded-lg hover:bg-gray-50"
                on:click={() => downloadAsJson(artifactData, `${raceId}-${runId.substring(0, 8)}.json`)}
              >
                Download JSON
              </button>
            {/if}
            <button
              type="button"
              class="px-3 py-1 text-xs border border-gray-300 rounded-lg hover:bg-gray-50"
              on:click={() => (showRawJson = !showRawJson)}
            >
              {showRawJson ? "Parsed View" : "Raw JSON"}
            </button>
          </div>
        </div>

        {#if artifactData}
          {#if showRawJson}
            <pre class="bg-gray-50 rounded-lg p-3 text-xs font-mono overflow-auto max-h-[600px] whitespace-pre-wrap break-words">{safeJsonStringify(artifactData, 300000).content}</pre>
          {:else}
            {@const d = artifactData}
            {#if typeof d === "object" && d !== null}
              <div class="space-y-4">
                <!-- Quick summary if it looks like RaceJSON -->
                {#if Array.isArray(d.candidates)}
                  {@const metrics = d.agent_metrics ?? d.output?.race_json?.agent_metrics ?? d.output?.agent_metrics ?? null}
                  <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <div class="bg-gray-50 rounded-lg p-3">
                      <p class="text-xs text-gray-500">Race</p>
                      <p class="text-sm font-semibold">{d.id ?? d.race_id ?? "—"}</p>
                    </div>
                    <div class="bg-gray-50 rounded-lg p-3">
                      <p class="text-xs text-gray-500">Candidates</p>
                      <p class="text-sm font-semibold">{d.candidates.length}</p>
                    </div>
                    <div class="bg-gray-50 rounded-lg p-3">
                      <p class="text-xs text-gray-500">Office</p>
                      <p class="text-sm font-semibold">{d.office ?? "—"}</p>
                    </div>
                    <div class="bg-gray-50 rounded-lg p-3">
                      <p class="text-xs text-gray-500">Updated</p>
                      <p class="text-sm font-semibold">{d.updated_utc ? new Date(d.updated_utc).toLocaleDateString() : "—"}</p>
                    </div>
                  </div>
                  {#if metrics}
                    <!-- Agent metrics card -->
                    <div class="border border-gray-200 rounded-lg p-4 bg-gray-50">
                      <h4 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Agent Metrics</h4>
                      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                        <div>
                          <p class="text-xs text-gray-400">Total Tokens</p>
                          <p class="text-sm font-semibold text-gray-800">{(metrics.total_tokens ?? 0).toLocaleString()}</p>
                        </div>
                        <div>
                          <p class="text-xs text-gray-400">Est. Cost</p>
                          <p class="text-sm font-semibold text-gray-800">{metrics.estimated_usd != null ? (metrics.estimated_usd < 0.001 ? '<$0.001' : `$${metrics.estimated_usd.toFixed(4)}`) : '—'}</p>
                        </div>
                        <div>
                          <p class="text-xs text-gray-400">Duration</p>
                          <p class="text-sm font-semibold text-gray-800">{metrics.duration_s != null ? `${Math.round(metrics.duration_s)}s` : '—'}</p>
                        </div>
                        <div>
                          <p class="text-xs text-gray-400">Primary Model</p>
                          <p class="text-sm font-semibold text-gray-800 truncate">{metrics.model ?? '—'}</p>
                        </div>
                      </div>
                      {#if metrics.model_breakdown && Object.keys(metrics.model_breakdown).length > 1}
                        <div class="border-t border-gray-200 pt-2">
                          <p class="text-xs text-gray-400 mb-1.5">Model Breakdown</p>
                          <div class="space-y-1">
                            {#each Object.entries(metrics.model_breakdown) as [model, counts]}
                              <div class="flex items-center justify-between text-xs">
                                <span class="font-mono text-gray-600 truncate max-w-48">{model}</span>
                                <span class="text-gray-500 shrink-0 ml-2">{breakdownTokens(counts).toLocaleString()} tok</span>
                              </div>
                            {/each}
                          </div>
                        </div>
                      {/if}
                    </div>
                  {/if}
                  <!-- Candidate cards -->
                  {#each d.candidates as candidate}
                    <div class="border border-gray-200 rounded-lg p-4">
                      <div class="flex items-center gap-3 mb-2">
                        <h4 class="text-sm font-bold text-gray-900">{candidate.name}</h4>
                        {#if candidate.party}
                          <span class="text-xs px-2 py-0.5 rounded-full {candidate.party === 'Democratic' ? 'bg-blue-100 text-blue-700' : candidate.party === 'Republican' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'}">{candidate.party}</span>
                        {/if}
                        {#if candidate.incumbent}
                          <span class="text-xs text-gray-500">Incumbent</span>
                        {/if}
                      </div>
                      {#if candidate.summary}
                        <p class="text-xs text-gray-600 mb-2 line-clamp-2">{candidate.summary}</p>
                      {/if}
                      {#if candidate.issues && typeof candidate.issues === "object"}
                        <div class="flex flex-wrap gap-1">
                          {#each Object.keys(candidate.issues) as issue}
                            <span class="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-700">{issue}</span>
                          {/each}
                        </div>
                      {/if}
                    </div>
                  {/each}
                {:else}
                  <!-- Generic object display -->
                  <pre class="bg-gray-50 rounded-lg p-3 text-xs font-mono overflow-auto max-h-[600px] whitespace-pre-wrap break-words">{safeJsonStringify(d, 300000).content}</pre>
                {/if}
              </div>
            {:else}
              <p class="text-sm text-gray-500">No structured output available</p>
            {/if}
          {/if}
        {:else if isRunning}
          <div class="flex items-center gap-2 p-6 text-gray-400 justify-center">
            <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <span class="text-sm">Output available when run completes…</span>
          </div>
        {:else}
          <p class="text-sm text-gray-400 py-4 text-center">
            {run.artifact_id ? "Click \"Load Artifact\" to view output" : "No output recorded for this run"}
          </p>
        {/if}
      </div>
    {/if}
  {/if}
</div>
