<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher, tick } from "svelte";
  import { PipelineApiService } from "$lib/services/pipelineApiService";
  import { formatDuration, getStatusClass, safeJsonStringify, downloadAsJson } from "$lib/utils/pipelineUtils";
  import type { RunInfo, RunStep, LogEntry, PipelineStepId } from "$lib/types";
  import { PIPELINE_STEPS } from "$lib/types";

  export let runId: string;
  export let isLive = false;
  export let liveLogs: LogEntry[] = [];
  export let liveProgress = 0;
  export let liveProgressMessage = "";
  export let liveElapsed = 0;

  const dispatch = createEventDispatcher<{ back: void; deleted: string }>();
  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";
  const apiService = new PipelineApiService(API_BASE);

  let run: RunInfo | null = null;
  let loading = true;
  let error = "";
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let showRawJson = false;
  type SectionId = "steps" | "logs" | "output" | "analysis";
  let activeSection: SectionId = "steps";
  let artifactData: any = null;
  let artifactLoading = false;
  type LogLevel = "all" | "info" | "warning" | "error";
  const LOG_LEVELS: LogLevel[] = ["all", "info", "warning", "error"];
  let logFilter: LogLevel = "all";
  let copiedRunId = false;
  let deleting = false;
  let logsContainer: HTMLDivElement;
  let autoScrollLogs = true;

  /** Canonical step order for sorting */
  const STEP_ORDER = PIPELINE_STEPS.map((s) => s.id);

  $: raceId = (run?.payload?.race_id as string) ?? runId;
  // A run is only "live" if the backend actually reports it as running/pending.
  // Never show the live spinner for a run the server has already completed.
  $: isRunning = run?.status === "running" || run?.status === "pending";
  $: isLiveAndRunning = isLive && isRunning;
  // Use live logs while the run is active; once done fall back to stored logs
  // then to agent_logs embedded in the artifact (GCS blobs strip logs).
  $: artifactAgentLogs = (() => {
    const logs = artifactData?.output?.agent_logs;
    if (!Array.isArray(logs)) return [];
    return logs.map((l: any) => ({
      level: (l.level ?? "info").toLowerCase(),
      message: l.message ?? String(l),
      timestamp: l.timestamp ?? "",
    })) as LogEntry[];
  })();
  // Extract the RaceJSON from the artifact regardless of wrapping structure
  $: artifactRaceJson = (() => {
    if (!artifactData || typeof artifactData !== "object") return null;
    const d = artifactData as any;
    // Wrapped: { step, input, options, output: { race_json: RaceJSON } }
    if (d.output?.race_json && Array.isArray(d.output.race_json.candidates)) return d.output.race_json;
    // Direct RaceJSON at top level
    if (Array.isArray(d.candidates)) return d;
    return null;
  })();
  // Extract agent metrics from wherever they live in the artifact
  $: artifactMetrics = (() => {
    if (!artifactData || typeof artifactData !== "object") return null;
    const d = artifactData as any;
    return d.output?.agent_metrics ?? d.output?.race_json?.agent_metrics ?? d.agent_metrics ?? null;
  })();
  $: runLogs = isLiveAndRunning ? liveLogs : ((run?.logs ?? []).length > 0 ? (run?.logs ?? []) : artifactAgentLogs);
  $: filteredLogs = logFilter === "all" ? runLogs : runLogs.filter((l) => l.level === logFilter);
  // Post-run analysis: broadcast as a single log entry starting with "[post-run analysis]"
  $: analysisContent = (() => {
    const all = [...liveLogs, ...(run?.logs ?? []), ...artifactAgentLogs];
    const found = all.find((l) => l.message?.startsWith("[post-run analysis]"));
    return found ? found.message.replace(/^\[post-run analysis\]\n?/, "").trim() : null;
  })();
  $: steps = run?.steps ?? [];
  // Filter to only pipeline sub-steps (exclude the top-level "agent" step), sorted by canonical order
  $: pipelineSteps = steps
    .filter((s) => s.name !== "agent")
    .sort((a, b) => {
      const ai = STEP_ORDER.indexOf(a.name as PipelineStepId);
      const bi = STEP_ORDER.indexOf(b.name as PipelineStepId);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    });
  $: hasPipelineSteps = pipelineSteps.length > 0;
  $: sections = [
    { id: "steps" as SectionId, label: `Steps (${pipelineSteps.length})` },
    { id: "logs" as SectionId, label: `Logs (${runLogs.length})` },
    { id: "output" as SectionId, label: "Output" },
    ...(analysisContent ? [{ id: "analysis" as SectionId, label: "✦ Analysis" }] : []),
  ];
  $: progress = isLiveAndRunning ? liveProgress : computeProgress(pipelineSteps);
  $: progressMsg = isLiveAndRunning ? liveProgressMessage : lastStepMessage(pipelineSteps);
  $: elapsed = isLiveAndRunning ? liveElapsed : (run?.duration_ms ? Math.floor(run.duration_ms / 1000) : 0);

  // Scroll the logs container to the bottom (called via tick to avoid Svelte reactive loop).
  // Must be a named function so that logsContainer is NOT syntactically inside the $: block;
  // if it were inline, Svelte would include logsContainer in the reactive dirty-bit mask and
  // the $$invalidate(logsContainer, ...) call made when setting scrollTop would re-trigger the
  // reactive statement on every scroll, creating an infinite loop that crashes the page.
  function scrollLogsToBottom() {
    if (logsContainer) logsContainer.scrollTop = logsContainer.scrollHeight;
  }

  // Auto-scroll logs when new entries arrive
  $: if (filteredLogs.length && autoScrollLogs && activeSection === "logs") {
    tick().then(scrollLogsToBottom);
  }

  function computeProgress(steps: RunStep[]): number {
    if (!steps.length) return 0;
    // Weight-based progress: sum weights of completed steps / total enabled weight
    const enabled = steps.filter((s) => s.status !== "skipped");
    if (!enabled.length) return 100;
    const totalWeight = enabled.reduce((sum, s) => sum + (s.weight || 1), 0);
    let doneWeight = 0;
    let partialWeight = 0;
    for (const s of enabled) {
      const w = s.weight || 1;
      if (s.status === "completed") doneWeight += w;
      else if (s.status === "running") partialWeight += w * ((s.progress_pct || 0) / 100);
    }
    return Math.min(98, Math.round(((doneWeight + partialWeight) / totalWeight) * 100));
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
      case "skipped": return "⊘";
      default: return "○";
    }
  }

  function stepColor(status: string): string {
    switch (status) {
      case "completed": return "text-green-600";
      case "running": return "text-blue-600";
      case "failed": return "text-red-600";
      case "skipped": return "text-content-faint opacity-50";
      default: return "text-content-faint";
    }
  }

  function statusBadge(status: string): string {
    switch (status) {
      case "completed": return "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300";
      case "running": return "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300";
      case "failed": return "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300";
      case "cancelled": return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300";
      case "skipped": return "bg-gray-100 text-gray-500 dark:bg-gray-800/30 dark:text-gray-500";
      case "pending": return "bg-surface-alt text-content-subtle";
      default: return "bg-surface-alt text-content-subtle";
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
      case "error": return "text-red-600 dark:text-red-400";
      case "warning": return "text-yellow-600 dark:text-yellow-400";
      case "debug": return "text-content-faint";
      default: return "text-content-muted";
    }
  }

  function breakdownTokens(counts: unknown): number {
    const c = counts as { prompt_tokens?: number; completion_tokens?: number };
    return (c?.prompt_tokens ?? 0) + (c?.completion_tokens ?? 0);
  }

  function sumBreakdownTokens(breakdown: unknown): number {
    if (!breakdown || typeof breakdown !== "object") return 0;
    return Object.values(breakdown as Record<string, unknown>).reduce((acc: number, c) => acc + breakdownTokens(c), 0);
  }

  function breakdownPct(breakdown: unknown, counts: unknown): number {
    const total = sumBreakdownTokens(breakdown);
    return total > 0 ? Math.round((breakdownTokens(counts) / total) * 100) : 0;
  }

  function candidateInitials(name: string): string {
    return name.split(" ").map((n: string) => n[0]).slice(0, 2).join("");
  }

  function issueConf(stance: unknown): string {
    return (stance as { confidence?: string })?.confidence ?? "unknown";
  }

  function issueStanceText(stance: unknown): string {
    return (stance as { stance?: string })?.stance ?? "No stance recorded";
  }

  function findCandidate(candidates: unknown[], name: string): { party?: string } | undefined {
    return (candidates as { name: string; party?: string }[]).find((c) => c.name === name);
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

  async function copyRunId() {
    try {
      await navigator.clipboard.writeText(runId);
      copiedRunId = true;
      setTimeout(() => (copiedRunId = false), 2000);
    } catch {}
  }

  async function handleDelete() {
    if (!run) return;
    const confirmMsg = isRunning
      ? `Force-delete running run ${runId.substring(0, 8)}… for ${raceId}? This will cancel and remove it immediately.`
      : `Delete run ${runId.substring(0, 8)}… for ${raceId}? This cannot be undone.`;
    if (!confirm(confirmMsg)) return;
    deleting = true;
    try {
      await apiService.deleteRaceRun(raceId, runId);
      dispatch("deleted", runId);
      dispatch("back");
    } catch (e) {
      error = `Delete failed: ${e}`;
    } finally {
      deleting = false;
    }
  }

  function handleLogsScroll() {
    if (!logsContainer) return;
    const { scrollTop, scrollHeight, clientHeight } = logsContainer;
    autoScrollLogs = scrollHeight - scrollTop - clientHeight < 40;
  }

  onMount(async () => {
    await loadRun();
    if (isRunning) {
      pollTimer = setInterval(loadRun, 3000);
    } else if (run?.artifact_id) {
      // Auto-load artifact for completed runs so logs are available immediately
      loadArtifact();
    }
  });

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  // If the run finishes, stop polling and load artifact
  $: if (run && !isRunning && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
    if (run.artifact_id && !artifactData) loadArtifact();
  }
</script>

<div class="space-y-4">
  <!-- Back button + header -->
  <div class="flex items-center gap-3">
    <button
      type="button"
      class="p-1.5 rounded-lg hover:bg-surface-alt text-content-subtle hover:text-content-muted"
      on:click={() => dispatch("back")}
      title="Back to runs"
    >
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
      </svg>
    </button>
    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-3">
        <h2 class="text-lg font-bold text-content truncate">{raceId}</h2>
        {#if run}
          <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold {statusBadge(run.status)}">
            {run.status}
          </span>
        {/if}
        {#if isLiveAndRunning}
          <span class="flex items-center gap-1 text-xs text-blue-600">
            <svg class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            Live
          </span>
        {/if}
      </div>
      <div class="flex items-center gap-4 mt-0.5 text-xs text-content-subtle">
        <button type="button" class="font-mono hover:text-content-muted transition-colors" on:click={copyRunId} title="Copy run ID">
          {copiedRunId ? '✓ Copied' : `Run ${runId.substring(0, 8)}`}
        </button>
        {#if run}
          <span>Started {formatTimestamp(run.started_at)}</span>
          {#if run.completed_at}
            <span>Finished {formatTimestamp(run.completed_at)}</span>
          {/if}
          {#if run.options?.research_model}
            <span class="font-mono">{run.options.research_model}</span>
          {/if}
          {#if run.options?.note}
            <span class="italic text-content-faint">"{run.options.note}"</span>
          {/if}
        {/if}
      </div>
    </div>
    <!-- Action buttons -->
    <div class="flex items-center gap-2 shrink-0">
      {#if run}
        <button
          type="button"
          class="p-1.5 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 disabled:opacity-40 transition-colors"
          on:click={handleDelete}
          disabled={deleting}
          title={isRunning ? "Force-delete this running run" : "Delete this run"}
        >
          <svg class="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      {/if}
    </div>
  </div>

  <!-- Run configuration summary (when options are interesting) -->
  {#if run && (run.options?.cheap_mode === false || run.options?.enable_review || run.options?.max_candidates || run.options?.target_no_info || run.options?.enabled_steps)}
    <div class="flex flex-wrap items-center gap-2 text-xs">
      {#if run.options.cheap_mode === false}
        <span class="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 font-medium">Full Mode</span>
      {/if}
      {#if run.options.enable_review}
        <span class="px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300 font-medium">AI Review</span>
      {/if}
      {#if run.options.max_candidates}
        <span class="px-2 py-0.5 rounded-full bg-surface-alt text-content-muted font-medium">Max {run.options.max_candidates} candidates</span>
      {/if}
      {#if run.options.target_no_info}
        <span class="px-2 py-0.5 rounded-full bg-surface-alt text-content-muted font-medium">No-info priority</span>
      {/if}
      {#if run.options.enabled_steps && run.options.enabled_steps.length < 7}
        <span class="px-2 py-0.5 rounded-full bg-surface-alt text-content-muted font-medium">{run.options.enabled_steps.length} steps enabled</span>
      {/if}
    </div>
  {/if}

  {#if loading}
    <div class="card p-8 text-center">
      <svg class="animate-spin h-6 w-6 mx-auto text-blue-500 mb-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
      </svg>
      <span class="text-sm text-content-subtle">Loading run details…</span>
    </div>
  {:else if error}
    <div class="card p-4 text-sm text-red-600">{error}</div>
  {:else if run}
    <!-- Progress bar -->
    <div class="card p-4">
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm text-content-muted font-medium">{progressMsg || "Waiting…"}</span>
        <div class="flex items-center gap-3 text-sm text-content-subtle">
          <span>{formatDuration(elapsed)}</span>
          <span class="font-semibold">{progress}%</span>
        </div>
      </div>
      <div class="w-full bg-stroke rounded-full h-2.5">
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
    <div class="flex gap-1 border-b border-stroke">
      {#each sections as sec}
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium transition-colors {activeSection === sec.id ? 'border-b-2 border-blue-600 text-blue-700 dark:text-blue-400' : 'text-content-subtle hover:text-content-muted'}"
          on:click={() => (activeSection = sec.id)}
        >
          {sec.label}
        </button>
      {/each}
    </div>

    <!-- Steps section -->
    {#if activeSection === "steps"}
      <div class="card p-0">
        {#if pipelineSteps.length > 0}
          <div class="divide-y divide-stroke">
            {#each pipelineSteps as step, i}
              {@const isSkipped = step.status === "skipped"}
              <div class="flex items-center gap-3 px-4 py-3 {isSkipped ? 'opacity-50' : ''}">
                <!-- Step number + icon -->
                <div class="flex items-center gap-2 shrink-0 w-8">
                  <span class="text-lg {stepColor(step.status)}">{stepIcon(step.status)}</span>
                </div>

                <!-- Step info -->
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium text-content {isSkipped ? 'line-through' : ''}">{step.label || step.name}</span>
                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase {statusBadge(step.status)}">{step.status}</span>
                  </div>
                  {#if step.status === "running" && step.progress_pct}
                    <div class="mt-1.5 flex items-center gap-2">
                      <div class="flex-1 h-1.5 bg-surface-alt rounded-full overflow-hidden">
                        <div class="h-full bg-blue-500 rounded-full transition-all duration-300" style="width: {step.progress_pct}%"></div>
                      </div>
                      <span class="text-[10px] text-content-subtle shrink-0">{step.progress_pct}%</span>
                    </div>
                  {/if}
                  {#if step.started_at && !isSkipped}
                    <div class="flex items-center gap-3 mt-0.5 text-[10px] text-content-faint">
                      <span>Started {formatTimestamp(step.started_at)}</span>
                      {#if step.completed_at}
                        <span>→ {formatTimestamp(step.completed_at)}</span>
                      {/if}
                    </div>
                  {/if}
                  {#if step.error}
                    <p class="mt-1 text-xs text-red-500 truncate">{step.error}</p>
                  {/if}
                </div>

                <!-- Duration -->
                <div class="shrink-0 text-right">
                  {#if step.duration_ms}
                    <span class="text-xs text-content-subtle">{formatDuration(Math.round(step.duration_ms / 1000))}</span>
                  {:else if step.status === "running"}
                    <span class="text-xs text-blue-500 animate-pulse">running…</span>
                  {:else if isSkipped}
                    <span class="text-xs text-content-faint">skipped</span>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {:else}
          <div class="text-center text-content-faint py-8 text-sm">
            {#if isRunning}
              Waiting for step data…
            {:else}
              No step data available for this run
            {/if}
          </div>
        {/if}
      </div>
    {/if}

    <!-- Logs section -->
    {#if activeSection === "logs"}
      <div class="card p-0">
        <div class="px-4 py-2 border-b border-stroke flex items-center gap-2">
          <span class="text-xs font-medium text-content-subtle">Filter:</span>
          {#each LOG_LEVELS as level}
            <button
              type="button"
              class="px-2 py-0.5 rounded text-xs font-medium transition-colors {logFilter === level ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' : 'text-content-subtle hover:bg-surface-alt'}"
              on:click={() => (logFilter = level)}
            >{level}</button>
          {/each}
          <span class="ml-auto text-xs text-content-faint">{filteredLogs.length} entries</span>
          <button
            type="button"
            class="px-2 py-0.5 rounded text-xs font-medium transition-colors {autoScrollLogs ? 'text-blue-600 dark:text-blue-400' : 'text-content-faint hover:text-content-subtle'}"
            on:click={() => { autoScrollLogs = !autoScrollLogs; if (autoScrollLogs && logsContainer) logsContainer.scrollTop = logsContainer.scrollHeight; }}
            title="{autoScrollLogs ? 'Auto-scroll on' : 'Auto-scroll off'}"
          >↓ Auto</button>
        </div>
        <div
          bind:this={logsContainer}
          on:scroll={handleLogsScroll}
          class="max-h-96 overflow-y-auto font-mono text-xs p-3 space-y-0.5 bg-surface-alt"
        >
          {#each filteredLogs as log}
            <div class="flex gap-2 leading-5">
              <span class="text-content-faint shrink-0 select-none">{log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : ""}</span>
              <span class="shrink-0 w-14 text-right font-semibold uppercase {logLevelClass(log.level)}">{log.level}</span>
              <span class="{logLevelClass(log.level)} break-all">{log.message}</span>
            </div>
          {:else}
            <div class="text-center text-content-faint py-6">No logs available</div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Output section -->
    {#if activeSection === "output"}
      <div class="card p-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold text-content-muted">
            {#if run.artifact_id}
              Artifact: <span class="font-mono text-content-subtle">{run.artifact_id}</span>
            {:else}
              Run Output
            {/if}
          </h3>
          <div class="flex items-center gap-2">
            {#if run.artifact_id && !artifactData}
              <button
                type="button"
                class="px-3 py-1 text-xs border border-stroke rounded-lg hover:bg-surface-alt disabled:opacity-40"
                disabled={artifactLoading}
                on:click={loadArtifact}
              >
                {artifactLoading ? "Loading…" : "Load Artifact"}
              </button>
            {/if}
            {#if artifactData}
              <button
                type="button"
                class="px-3 py-1 text-xs border border-stroke rounded-lg hover:bg-surface-alt"
                on:click={() => downloadAsJson(artifactData, `${raceId}-${runId.substring(0, 8)}.json`)}
              >
                Download JSON
              </button>
            {/if}
            <button
              type="button"
              class="px-3 py-1 text-xs border border-stroke rounded-lg hover:bg-surface-alt"
              on:click={() => (showRawJson = !showRawJson)}
            >
              {showRawJson ? "Parsed View" : "Raw JSON"}
            </button>
          </div>
        </div>

        {#if artifactLoading}
          <div class="py-6 text-center text-sm text-content-faint">Loading output…</div>
        {:else if artifactData}
          {#if showRawJson}
            <pre class="bg-surface-alt rounded-lg p-3 text-xs font-mono overflow-auto max-h-[600px] whitespace-pre-wrap break-words text-content">{safeJsonStringify(artifactData).content}</pre>
          {:else if artifactRaceJson}
            {@const rj = artifactRaceJson}
            <div class="space-y-4">
              <!-- Race header card -->
              <div class="rounded-xl border border-stroke p-4 bg-gradient-to-br from-surface to-surface-alt">
                <div class="flex items-start justify-between gap-4">
                  <div class="flex-1 min-w-0">
                    <h3 class="text-base font-bold text-content">{rj.title ?? rj.id}</h3>
                    <div class="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1 text-xs text-content-subtle">
                      {#if rj.office}<span class="font-medium">{rj.office}</span>{/if}
                      {#if rj.jurisdiction}<span class="text-content-faint">·</span><span>{rj.jurisdiction}</span>{/if}
                      {#if rj.election_date}<span class="text-content-faint">·</span><span>Election: {rj.election_date}</span>{/if}
                    </div>
                    {#if rj.description}
                      <p class="mt-2 text-xs text-content-muted leading-relaxed">{rj.description}</p>
                    {/if}
                  </div>
                  <div class="flex flex-col items-end gap-1.5 shrink-0">
                    {#if rj.validation_grade}
                      <div class="flex items-center gap-2 bg-surface rounded-lg px-3 py-1.5 border border-stroke">
                        <span class="text-[10px] text-content-faint uppercase tracking-wide">Quality</span>
                        <span class="text-2xl font-black leading-none {rj.validation_grade.grade === 'A' ? 'text-green-500' : rj.validation_grade.grade === 'B' ? 'text-lime-500' : rj.validation_grade.grade === 'C' ? 'text-yellow-500' : rj.validation_grade.grade === 'D' ? 'text-orange-500' : 'text-red-500'}">{rj.validation_grade.grade}</span>
                        <span class="text-xs text-content-subtle font-semibold">{rj.validation_grade.score}/100</span>
                      </div>
                      {#if rj.validation_grade.summary}
                        <p class="text-[10px] text-content-faint text-right max-w-40 leading-snug">{rj.validation_grade.summary}</p>
                      {/if}
                    {/if}
                    <span class="text-xs text-content-faint">{rj.candidates.length} candidate{rj.candidates.length !== 1 ? 's' : ''}</span>
                    {#if rj.updated_utc}
                      <span class="text-[10px] text-content-faint">Updated {new Date(rj.updated_utc).toLocaleString()}</span>
                    {/if}
                  </div>
                </div>
              </div>

              <!-- Agent metrics -->
              {#if artifactMetrics}
                <div class="rounded-xl border border-stroke p-4">
                  <h4 class="text-[10px] font-semibold uppercase tracking-wider text-content-faint mb-3">Agent Metrics</h4>
                  <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-3">
                    <div>
                      <p class="text-[10px] text-content-faint uppercase tracking-wide">Est. Cost</p>
                      <p class="text-xl font-bold text-content">{artifactMetrics.estimated_usd != null ? (artifactMetrics.estimated_usd < 0.001 ? '<$0.001' : `$${artifactMetrics.estimated_usd.toFixed(3)}`) : '—'}</p>
                    </div>
                    <div>
                      <p class="text-[10px] text-content-faint uppercase tracking-wide">Tokens</p>
                      <p class="text-xl font-bold text-content">{(artifactMetrics.total_tokens ?? 0).toLocaleString()}</p>
                    </div>
                    <div>
                      <p class="text-[10px] text-content-faint uppercase tracking-wide">Duration</p>
                      <p class="text-xl font-bold text-content">{artifactMetrics.duration_s != null ? `${Math.round(artifactMetrics.duration_s)}s` : '—'}</p>
                    </div>
                    <div>
                      <p class="text-[10px] text-content-faint uppercase tracking-wide">Model</p>
                      <p class="text-sm font-semibold text-content truncate">{artifactMetrics.model ?? '—'}</p>
                    </div>
                  </div>
                  {#if artifactMetrics.model_breakdown && Object.keys(artifactMetrics.model_breakdown).length > 0}
                    <div class="border-t border-stroke pt-3">
                      <p class="text-[10px] text-content-faint uppercase tracking-wide mb-2">Token Usage by Model</p>
                      <div class="space-y-1.5">
                        {#each Object.entries(artifactMetrics.model_breakdown) as [model, counts]}
                          {@const tok = breakdownTokens(counts)}
                          {@const pct = breakdownPct(artifactMetrics.model_breakdown, counts)}
                          <div class="flex items-center gap-2 text-xs">
                            <span class="font-mono text-content-subtle w-44 truncate shrink-0">{model}</span>
                            <div class="flex-1 h-1.5 bg-surface-alt rounded-full overflow-hidden">
                              <div class="h-full bg-blue-500 rounded-full" style="width: {pct}%"></div>
                            </div>
                            <span class="text-content-faint shrink-0 w-20 text-right">{tok.toLocaleString()} tok</span>
                          </div>
                        {/each}
                      </div>
                    </div>
                  {/if}
                </div>
              {/if}

              <!-- Candidates -->
              <div>
                <h4 class="text-[10px] font-semibold uppercase tracking-wider text-content-faint mb-2">Candidates ({rj.candidates.length})</h4>
                <div class="space-y-3">
                  {#each rj.candidates as candidate}
                    {@const issueEntries = candidate.issues ? Object.entries(candidate.issues) : []}
                    {@const partyBorder = candidate.party === 'Democratic' ? 'border-l-blue-400' : candidate.party === 'Republican' ? 'border-l-red-400' : 'border-l-stroke'}
                    <div class="rounded-xl border border-stroke border-l-4 {partyBorder} p-4 bg-surface">
                      <!-- Header row -->
                      <div class="flex items-start gap-3">
                        <!-- Avatar -->
                        <div class="shrink-0">
                          {#if candidate.image_url}
                            <img src={candidate.image_url} alt={candidate.name} class="w-11 h-11 rounded-full object-cover border border-stroke" />
                          {:else}
                            <div class="w-11 h-11 rounded-full flex items-center justify-center text-sm font-bold text-white {candidate.party === 'Democratic' ? 'bg-blue-500' : candidate.party === 'Republican' ? 'bg-red-500' : 'bg-content-subtle'}">
                              {candidateInitials(candidate.name)}
                            </div>
                          {/if}
                        </div>
                        <!-- Info -->
                        <div class="flex-1 min-w-0">
                          <div class="flex items-center flex-wrap gap-2">
                            <h4 class="text-sm font-bold text-content">{candidate.name}</h4>
                            {#if candidate.party}
                              <span class="text-xs px-2 py-0.5 rounded-full font-medium {candidate.party === 'Democratic' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' : candidate.party === 'Republican' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' : 'bg-surface-alt text-content-muted'}">{candidate.party}</span>
                            {/if}
                            {#if candidate.incumbent}
                              <span class="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 font-medium">Incumbent</span>
                            {/if}
                          </div>
                          {#if candidate.summary}
                            <p class="mt-1 text-xs text-content-muted leading-relaxed line-clamp-3">{candidate.summary}</p>
                          {/if}
                        </div>
                        <!-- External links -->
                        <div class="flex items-center gap-1.5 shrink-0 flex-wrap justify-end">
                          {#if candidate.website}
                            <a href={String(candidate.website)} target="_blank" rel="noopener noreferrer" class="p-1.5 rounded-lg text-content-faint hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors" title="Official website">
                              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                            </a>
                          {/if}
                          {#each (candidate.links ?? []).slice(0, 4) as link}
                            <a href={link.url} target="_blank" rel="noopener noreferrer" class="text-[10px] px-1.5 py-0.5 rounded border border-stroke bg-surface-alt text-content-subtle hover:text-content-muted hover:border-content-faint transition-colors capitalize" title={link.title}>{link.type}</a>
                          {/each}
                        </div>
                      </div>

                      <!-- Issues coverage grid -->
                      {#if issueEntries.length > 0}
                        <div class="mt-3 pt-3 border-t border-stroke">
                          <p class="text-[10px] text-content-faint uppercase tracking-wide mb-2">Issue Coverage ({issueEntries.length}/12)</p>
                          <div class="flex flex-wrap gap-1.5">
                            {#each issueEntries as [issueName, stance]}
                              {@const conf = issueConf(stance)}
                              <div
                                class="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border {conf === 'high' ? 'border-green-300 bg-green-50 dark:border-green-800 dark:bg-green-900/20' : conf === 'medium' ? 'border-yellow-300 bg-yellow-50 dark:border-yellow-800 dark:bg-yellow-900/20' : conf === 'low' ? 'border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-900/20' : 'border-stroke bg-surface-alt'}"
                                title="{issueName}: {issueStanceText(stance)}"
                              >
                                <span class="w-1.5 h-1.5 rounded-full shrink-0 {conf === 'high' ? 'bg-green-500' : conf === 'medium' ? 'bg-yellow-500' : conf === 'low' ? 'bg-red-500' : 'bg-content-faint'}"></span>
                                <span class="text-content-muted">{issueName}</span>
                              </div>
                            {/each}
                          </div>
                        </div>
                      {/if}

                      <!-- Finance + voting record -->
                      {#if candidate.donor_summary || candidate.voting_summary}
                        <div class="mt-3 pt-3 border-t border-stroke grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {#if candidate.donor_summary}
                            <div>
                              <p class="text-[10px] text-content-faint uppercase tracking-wide mb-1">Finance</p>
                              <p class="text-xs text-content-muted leading-relaxed line-clamp-2">{candidate.donor_summary}</p>
                              {#if candidate.donor_source_url}
                                <a href={candidate.donor_source_url} target="_blank" rel="noopener noreferrer" class="text-[10px] text-blue-600 hover:underline mt-0.5 inline-block">View source →</a>
                              {/if}
                            </div>
                          {/if}
                          {#if candidate.voting_summary}
                            <div>
                              <p class="text-[10px] text-content-faint uppercase tracking-wide mb-1">Voting Record</p>
                              <p class="text-xs text-content-muted leading-relaxed line-clamp-2">{candidate.voting_summary}</p>
                              {#if candidate.voting_source_url}
                                <a href={candidate.voting_source_url} target="_blank" rel="noopener noreferrer" class="text-[10px] text-blue-600 hover:underline mt-0.5 inline-block">View source →</a>
                              {/if}
                            </div>
                          {/if}
                        </div>
                      {/if}
                    </div>
                  {/each}
                </div>
              </div>

              <!-- Polling data -->
              {#if rj.polling && rj.polling.length > 0}
                <div>
                  <h4 class="text-[10px] font-semibold uppercase tracking-wider text-content-faint mb-2">Polling ({rj.polling.length})</h4>
                  <div class="space-y-2">
                    {#each rj.polling as poll}
                      <div class="rounded-xl border border-stroke p-3">
                        <div class="flex items-center justify-between mb-3">
                          <span class="text-xs font-semibold text-content">{poll.pollster}</span>
                          <div class="flex items-center gap-3 text-xs text-content-faint">
                            {#if poll.date}<span>{poll.date}</span>{/if}
                            {#if poll.sample_size}<span>n={poll.sample_size.toLocaleString()}</span>{/if}
                            {#if poll.source_url}<a href={poll.source_url} target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:underline">Source</a>{/if}
                          </div>
                        </div>
                        {#each poll.matchups as matchup}
                          <div class="space-y-1.5">
                            {#each matchup.candidates as name, i}
                              {@const pct = matchup.percentages?.[i] ?? 0}
                              {@const candidateObj = findCandidate(rj.candidates, name)}
                              <div class="flex items-center gap-2 text-xs">
                                <span class="w-28 text-content-muted truncate shrink-0">{name}</span>
                                <div class="flex-1 h-4 bg-surface-alt rounded-md overflow-hidden">
                                  <div
                                    class="h-full rounded-md transition-all duration-500 {candidateObj?.party === 'Democratic' ? 'bg-blue-500' : candidateObj?.party === 'Republican' ? 'bg-red-500' : 'bg-content-subtle'}"
                                    style="width: {pct}%"
                                  ></div>
                                </div>
                                <span class="w-8 text-right font-semibold text-content shrink-0">{pct}%</span>
                              </div>
                            {/each}
                          </div>
                        {/each}
                      </div>
                    {/each}
                  </div>
                </div>
              {:else if rj.polling_note}
                <div class="rounded-xl border border-stroke p-3 text-xs text-content-faint italic">
                  Polling: {rj.polling_note}
                </div>
              {/if}

              <!-- AI Reviews -->
              {#if rj.reviews && rj.reviews.length > 0}
                <div>
                  <h4 class="text-[10px] font-semibold uppercase tracking-wider text-content-faint mb-2">AI Reviews ({rj.reviews.length})</h4>
                  <div class="space-y-2">
                    {#each rj.reviews as review}
                      <div class="rounded-xl border border-stroke p-3">
                        <div class="flex items-start justify-between gap-2">
                          <div class="flex items-center gap-2 flex-wrap">
                            <span class="text-xs font-semibold text-content font-mono">{review.model}</span>
                            <span class="text-xs px-1.5 py-0.5 rounded font-medium {review.verdict === 'approved' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : review.verdict === 'needs_revision' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'}">{review.verdict}</span>
                          </div>
                          {#if review.score != null}
                            <span class="text-sm font-bold text-content shrink-0">{review.score}/100</span>
                          {/if}
                        </div>
                        {#if review.summary}
                          <p class="mt-1.5 text-xs text-content-muted leading-relaxed">{review.summary}</p>
                        {/if}
                        {#if review.flags && review.flags.length > 0}
                          <div class="mt-2 space-y-1 border-t border-stroke pt-2">
                            {#each review.flags as flag}
                              <div class="text-xs flex items-start gap-1.5">
                                <span class="shrink-0 mt-0.5 {flag.severity === 'error' ? 'text-red-500' : flag.severity === 'warning' ? 'text-yellow-500' : 'text-blue-500'}">●</span>
                                <span class="text-content-muted"><span class="font-medium">{flag.field}:</span> {flag.concern}</span>
                              </div>
                            {/each}
                          </div>
                        {/if}
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}

              <!-- Post-run process analysis (inline in output view) -->
              {#if analysisContent}
                <div class="rounded-xl border border-purple-200 dark:border-purple-800/50 overflow-hidden">
                  <div class="px-4 py-2.5 bg-purple-50 dark:bg-purple-900/20 border-b border-purple-200 dark:border-purple-800/50 flex items-center gap-2">
                    <svg class="w-3.5 h-3.5 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                    <span class="text-xs font-semibold text-purple-700 dark:text-purple-300 uppercase tracking-wide">Post-Run Process Analysis</span>
                    <span class="text-xs text-purple-400 dark:text-purple-500 ml-auto">Pipeline improvement suggestions</span>
                  </div>
                  <div class="p-4 text-sm text-content-muted leading-relaxed whitespace-pre-wrap">{analysisContent}</div>
                </div>
              {/if}
            </div>
          {:else}
            <!-- Generic fallback for non-RaceJSON artifacts -->
            <pre class="bg-surface-alt rounded-lg p-3 text-xs font-mono overflow-auto max-h-[600px] whitespace-pre-wrap break-words text-content">{safeJsonStringify(artifactData).content}</pre>
          {/if}
        {:else if isLiveAndRunning}
          <div class="flex items-center gap-2 p-6 text-content-faint justify-center">
            <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <span class="text-sm">Output available when run completes…</span>
          </div>
        {:else}
          <p class="text-sm text-content-faint py-4 text-center">
            {run.artifact_id ? "Click \"Load Artifact\" to view output" : "No output recorded for this run"}
          </p>
        {/if}
      </div>
    {/if}

    <!-- Analysis section -->
    {#if activeSection === "analysis"}
      <div class="card p-0 overflow-hidden">
        <div class="px-4 py-2.5 border-b border-stroke bg-purple-50 dark:bg-purple-900/20 flex items-center gap-2.5">
          <svg class="w-3.5 h-3.5 text-purple-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <span class="text-xs font-semibold text-purple-700 dark:text-purple-300 uppercase tracking-wide">Post-Run Process Analysis</span>
          <span class="text-xs text-purple-400 dark:text-purple-500 ml-auto">Pipeline improvement suggestions</span>
        </div>
        {#if analysisContent}
          <div class="p-5 text-sm text-content-muted leading-relaxed whitespace-pre-wrap">{analysisContent}</div>
        {:else}
          <div class="p-6 text-center text-sm text-content-faint">Analysis runs after the pipeline completes. Keep the page open to capture it.</div>
        {/if}
      </div>
    {/if}
  {/if}
</div>
