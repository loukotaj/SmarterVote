<script lang="ts">
  import { onMount } from "svelte";
  import type { ChamberForecasts } from "$lib/types";
  import type { PipelineApiService } from "$lib/services/pipelineApiService";

  export let apiService: PipelineApiService;

  const DEFAULT_MODEL = "google/gemini-2.5-flash";

  let loading = true;
  let saving = false;
  let generating = false;
  let publishing = false;
  let error = "";
  let notice: { type: "success" | "error"; message: string } | null = null;
  let published: ChamberForecasts | null = null;
  let draft: ChamberForecasts | null = null;
  let model = DEFAULT_MODEL;

  let house = "";
  let senate = "";
  let governors = "";
  let schemaVersion = "chamber_forecasts.v2";
  let chambersJson = "{}";

  function errorMessage(e: unknown): string {
    return e instanceof Error ? e.message : String(e);
  }

  function setNotice(type: "success" | "error", message: string) {
    notice = { type, message };
  }

  function applyForecast(value: ChamberForecasts | null) {
    house = value?.house ?? "";
    senate = value?.senate ?? "";
    governors = value?.governors ?? "";
    schemaVersion = value?.schema_version ?? "chamber_forecasts.v2";
    chambersJson = JSON.stringify(value?.chambers ?? {}, null, 2);
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
      applyForecast(draft ?? published);
    } catch (e) {
      error = errorMessage(e);
    } finally {
      loading = false;
    }
  }

  function buildPayload() {
    let chambers: Record<string, unknown> | undefined;
    try {
      const parsed = JSON.parse(chambersJson || "{}");
      if (
        parsed === null ||
        Array.isArray(parsed) ||
        typeof parsed !== "object"
      ) {
        throw new Error("Chambers JSON must be an object.");
      }
      chambers = parsed as Record<string, unknown>;
    } catch (e) {
      throw new Error(`Invalid chambers JSON: ${errorMessage(e)}`);
    }
    return {
      house_narrative: house.trim(),
      senate_narrative: senate.trim(),
      governors_narrative: governors.trim(),
      schema_version: schemaVersion.trim() || "chamber_forecasts.v2",
      chambers,
    };
  }

  async function saveDraft() {
    saving = true;
    notice = null;
    try {
      const payload = buildPayload();
      const result = await apiService.saveChamberForecastDraft(payload);
      draft = {
        house: payload.house_narrative,
        senate: payload.senate_narrative,
        governors: payload.governors_narrative,
        schema_version: payload.schema_version,
        chambers: payload.chambers as ChamberForecasts["chambers"],
        updated_at: result.updated_at,
      };
      setNotice("success", "Chamber forecast draft saved.");
    } catch (e) {
      setNotice("error", `Save failed: ${errorMessage(e)}`);
    } finally {
      saving = false;
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
      applyForecast(draft);
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
</script>

<div class="space-y-4">
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div>
      <h2 class="text-lg font-semibold text-content">Chamber Forecasts</h2>
      <p class="text-sm text-content-subtle">
        Manage House, Senate, and Governors forecast narratives.
      </p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <input
        type="text"
        bind:value={model}
        class="w-64 rounded border border-stroke bg-surface px-3 py-2 text-sm text-content"
        aria-label="Generation model"
      />
      <button
        type="button"
        class="rounded border border-stroke px-3 py-2 text-sm text-content hover:bg-surface-alt disabled:opacity-50"
        disabled={loading || generating}
        on:click={generateDraft}
      >
        {generating ? "Generating..." : "Generate Draft"}
      </button>
      <button
        type="button"
        class="rounded border border-stroke px-3 py-2 text-sm text-content hover:bg-surface-alt disabled:opacity-50"
        disabled={loading}
        on:click={loadForecasts}
      >
        Refresh
      </button>
    </div>
  </div>

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
    <div class="grid gap-3 text-sm md:grid-cols-3">
      <div class="rounded-lg border border-stroke bg-surface p-3">
        <div class="text-xs uppercase tracking-wide text-content-faint">
          Published
        </div>
        <div class="mt-1 font-medium text-content">
          {published?.updated_at ?? "No published forecast loaded"}
        </div>
      </div>
      <div class="rounded-lg border border-stroke bg-surface p-3">
        <div class="text-xs uppercase tracking-wide text-content-faint">
          Draft
        </div>
        <div class="mt-1 font-medium text-content">
          {draft?.updated_at ?? "No draft forecast loaded"}
        </div>
      </div>
      <div class="rounded-lg border border-stroke bg-surface p-3">
        <label
          for="schema-version"
          class="text-xs uppercase tracking-wide text-content-faint"
        >
          Schema
        </label>
        <input
          id="schema-version"
          bind:value={schemaVersion}
          class="mt-1 w-full rounded border border-stroke bg-surface px-2 py-1 text-sm text-content"
        />
      </div>
    </div>

    <div class="grid gap-4 lg:grid-cols-3">
      <label class="block space-y-1">
        <span class="text-sm font-semibold text-content">House narrative</span>
        <textarea
          bind:value={house}
          rows="8"
          class="w-full rounded-lg border border-stroke bg-surface p-3 text-sm text-content"
        />
      </label>
      <label class="block space-y-1">
        <span class="text-sm font-semibold text-content">Senate narrative</span>
        <textarea
          bind:value={senate}
          rows="8"
          class="w-full rounded-lg border border-stroke bg-surface p-3 text-sm text-content"
        />
      </label>
      <label class="block space-y-1">
        <span class="text-sm font-semibold text-content"
          >Governors narrative</span
        >
        <textarea
          bind:value={governors}
          rows="8"
          class="w-full rounded-lg border border-stroke bg-surface p-3 text-sm text-content"
        />
      </label>
    </div>

    <label class="block space-y-1">
      <span class="text-sm font-semibold text-content"
        >Structured chamber JSON</span
      >
      <textarea
        bind:value={chambersJson}
        rows="16"
        spellcheck="false"
        class="w-full rounded-lg border border-stroke bg-surface p-3 font-mono text-xs text-content"
      />
    </label>

    <div class="flex flex-wrap justify-end gap-2">
      <button
        type="button"
        class="rounded border border-stroke px-4 py-2 text-sm text-content hover:bg-surface-alt disabled:opacity-50"
        disabled={saving}
        on:click={saveDraft}
      >
        {saving ? "Saving..." : "Save Draft"}
      </button>
      <button
        type="button"
        class="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        disabled={publishing || !draft}
        on:click={publishDraft}
      >
        {publishing ? "Publishing..." : "Publish Draft"}
      </button>
    </div>
  {/if}
</div>
