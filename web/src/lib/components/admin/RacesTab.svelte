<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte";
  import { PipelineApiService } from "$lib/services/pipelineApiService";
  import QualityBadge from "./QualityBadge.svelte";
  import type { RaceRecord, RaceStatusType } from "$lib/types";

  export let onSelectRace: (race: RaceRecord) => void = () => {};
  export let onBatchQueue: (raceIds: string[]) => void = () => {};
  export async function refresh() {
    loading = true;
    await loadData();
  }

  const dispatch = createEventDispatcher<{ addRaces: string }>();
  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";
  const apiService = new PipelineApiService(API_BASE);

  let rows: RaceRecord[] = [];
  let filteredRows: RaceRecord[] = [];
  let loading = true;
  let error = "";
  let search = "";
  let statusFilter: RaceStatusType | "all" = "all";
  let sortKey: keyof RaceRecord = "draft_updated_at";
  let sortAsc = false;
  let selected = new Set<string>();
  let publishing = new Set<string>();
  let bulkPublishing = false;
  let addInput = "";

  async function loadData() {
    try {
      error = "";
      rows = await apiService.listRaces();
      applyFilterSort();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  function applyFilterSort() {
    let result = rows.filter((r) => {
      if (statusFilter !== "all" && r.status !== statusFilter) return false;
      if (!search) return true;
      const s = search.toLowerCase();
      return (
        r.race_id.toLowerCase().includes(s) ||
        (r.title ?? "").toLowerCase().includes(s) ||
        (r.jurisdiction ?? "").toLowerCase().includes(s)
      );
    });

    result.sort((a, b) => {
      const av = (a as any)[sortKey];
      const bv = (b as any)[sortKey];
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return sortAsc ? av - bv : bv - av;
      return sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });

    filteredRows = result;
  }

  $: if (rows) applyFilterSort();
  $: if (search !== undefined || statusFilter) applyFilterSort();

  function toggleSort(key: keyof RaceRecord) {
    if (sortKey === key) sortAsc = !sortAsc;
    else { sortKey = key; sortAsc = false; }
  }

  function toggleSelect(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    selected = next;
  }

  function toggleAll() {
    if (selected.size === filteredRows.length) selected = new Set();
    else selected = new Set(filteredRows.map((r) => r.race_id));
  }

  function handleBatchAction() {
    if (selected.size < 1) return;
    onBatchQueue([...selected]);
    selected = new Set();
  }

  function handleAddRaces() {
    const raw = addInput.trim();
    if (!raw) return;
    dispatch("addRaces", raw);
    addInput = "";
  }

  function handleAddKeydown(e: KeyboardEvent) {
    if (e.key === "Enter") handleAddRaces();
  }

  function hasPendingDraft(row: RaceRecord): boolean {
    return (
      !!row.draft_updated_at &&
      (row.status === "draft" ||
        (row.status === "published" && !!row.published_at && row.draft_updated_at > row.published_at))
    );
  }

  $: selectedWithDrafts = [...selected].filter((id) => {
    const row = rows.find((r) => r.race_id === id);
    return row && hasPendingDraft(row);
  });

  async function handleBulkPublish() {
    if (selectedWithDrafts.length === 0) return;
    if (!confirm(`Publish ${selectedWithDrafts.length} race${selectedWithDrafts.length !== 1 ? "s" : ""}?`)) return;
    bulkPublishing = true;
    try {
      const result = await apiService.batchPublishRaces(selectedWithDrafts);
      if (result.errors.length > 0) {
        error = `Published ${result.published.length}, failed: ${result.errors.map((e) => `${e.race_id}: ${e.error}`).join(", ")}`;
      }
      selected = new Set();
      await loadData();
    } catch (e) {
      error = `Bulk publish failed: ${e}`;
    } finally {
      bulkPublishing = false;
    }
  }

  async function handlePublish(race_id: string) {
    publishing = new Set([...publishing, race_id]);
    try {
      await apiService.publishRace(race_id);
      await loadData();
    } catch (e) {
      error = `Publish failed: ${e}`;
    } finally {
      const next = new Set(publishing);
      next.delete(race_id);
      publishing = next;
    }
  }

  async function handleUnpublish(race_id: string) {
    if (!confirm(`Unpublish "${race_id}"? Removes from public site but keeps the draft.`)) return;
    publishing = new Set([...publishing, race_id]);
    try {
      await apiService.unpublishRaceRecord(race_id);
      await loadData();
    } catch (e) {
      error = `Unpublish failed: ${e}`;
    } finally {
      const next = new Set(publishing);
      next.delete(race_id);
      publishing = next;
    }
  }

  async function handleDelete(race_id: string) {
    if (!confirm(`Delete "${race_id}" entirely? This cannot be undone.`)) return;
    try {
      await apiService.deleteRaceRecord(race_id);
      await loadData();
    } catch (e) {
      error = `Delete failed: ${e}`;
    }
  }

  function handlePreview(race_id: string) {
    window.open(`/races/${race_id}?draft=true`, "_blank");
  }

  function sortIcon(key: keyof RaceRecord) {
    if (sortKey !== key) return "↕";
    return sortAsc ? "↑" : "↓";
  }

  function statusBadgeClass(s: RaceStatusType) {
    switch (s) {
      case "published": return "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200";
      case "draft": return "bg-amber-100 dark:bg-amber-900 text-amber-800 dark:text-amber-200";
      case "queued": return "bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200";
      case "running": return "bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200";
      case "failed": return "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200";
      default: return "bg-surface-alt text-content-muted";
    }
  }

  function freshnessBadgeClass(f?: string) {
    switch (f) {
      case "fresh": return "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200";
      case "recent": return "bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200";
      case "aging": return "bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200";
      case "stale": return "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200";
      default: return "bg-surface-alt text-content-muted";
    }
  }

  function formatDate(s?: string) {
    if (!s) return "—";
    return new Date(s).toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  const STATUS_OPTIONS: { value: RaceStatusType | "all"; label: string }[] = [
    { value: "all", label: "All" },
    { value: "published", label: "Published" },
    { value: "draft", label: "Draft" },
    { value: "queued", label: "Queued" },
    { value: "running", label: "Running" },
    { value: "failed", label: "Failed" },
    { value: "empty", label: "Empty" },
  ];

  onMount(loadData);
</script>

<div class="space-y-4">
  <!-- Add races input -->
  <div class="card p-3">
    <div class="flex gap-2">
      <input
        type="text"
        bind:value={addInput}
        on:keydown={handleAddKeydown}
        placeholder="Add races: ga-senate-2026, tx-governor-2026…"
        class="flex-1 px-3 py-2 border border-stroke rounded-lg text-sm font-mono bg-surface text-content focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
      />
      <button
        type="button"
        on:click={handleAddRaces}
        disabled={!addInput.trim()}
        class="btn-primary px-4 py-2 text-sm rounded-lg whitespace-nowrap disabled:opacity-40 disabled:cursor-not-allowed"
      >
        + Queue
      </button>
    </div>
    <p class="mt-1 text-xs text-content-faint">Comma-separate IDs · <kbd class="px-1 py-0.5 bg-surface-alt rounded text-xs">Enter</kbd> to add</p>
  </div>

  <!-- Toolbar -->
  <div class="flex items-center justify-between gap-3 flex-wrap">
    <div class="flex items-center gap-2 flex-1 min-w-0">
      <input
        type="search"
        bind:value={search}
        placeholder="Search by race ID, title, jurisdiction…"
        class="flex-1 min-w-48 px-3 py-2 text-sm border border-stroke rounded-lg bg-surface text-content focus:outline-none focus:border-blue-500"
      />
      <select
        bind:value={statusFilter}
        class="px-3 py-2 text-sm border border-stroke rounded-lg bg-surface text-content focus:outline-none focus:border-blue-500"
      >
        {#each STATUS_OPTIONS as opt}
          <option value={opt.value}>{opt.label}</option>
        {/each}
      </select>
    </div>
    <div class="flex items-center space-x-2">
      {#if selected.size > 0}
        <button
          type="button"
          class="btn-primary px-4 py-2 text-sm rounded-lg"
          on:click={handleBatchAction}
        >
          Queue {selected.size} Selected
        </button>
        {#if selectedWithDrafts.length > 0}
          <button
            type="button"
            class="px-4 py-2 text-sm rounded-lg border border-green-300 dark:border-green-700 text-green-700 dark:text-green-300 hover:bg-green-50 dark:hover:bg-green-900/20 font-medium disabled:opacity-40"
            disabled={bulkPublishing}
            on:click={handleBulkPublish}
          >
            {bulkPublishing ? "Publishing…" : `Publish ${selectedWithDrafts.length} Draft${selectedWithDrafts.length !== 1 ? "s" : ""}`}
          </button>
        {/if}
      {/if}
      <button
        type="button"
        class="px-3 py-2 text-sm border border-stroke rounded-lg hover:bg-surface-alt text-content"
        on:click={loadData}
      >
        Refresh
      </button>
    </div>
  </div>

  {#if error}
    <div class="card p-4 text-sm text-red-600">{error}</div>
  {:else if loading}
    <div class="card p-8 text-center text-content-faint text-sm">Loading races…</div>
  {:else if filteredRows.length === 0}
    <div class="card p-8 text-center text-content-faint text-sm">No races found</div>
  {:else}
    <div class="card overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="bg-surface-alt border-b border-stroke">
            <tr>
              <th class="pl-4 pr-2 py-3 text-left">
                <input
                  type="checkbox"
                  checked={selected.size === filteredRows.length && filteredRows.length > 0}
                  indeterminate={selected.size > 0 && selected.size < filteredRows.length}
                  on:change={toggleAll}
                  class="rounded border-stroke"
                />
              </th>
              <th class="px-3 py-3 text-left font-medium text-content-muted cursor-pointer hover:text-content whitespace-nowrap" on:click={() => toggleSort("race_id")}>
                Race ID {sortIcon("race_id")}
              </th>
              <th class="px-3 py-3 text-left font-medium text-content-muted cursor-pointer hover:text-content whitespace-nowrap" on:click={() => toggleSort("title")}>
                Title {sortIcon("title")}
              </th>
              <th class="px-3 py-3 text-left font-medium text-content-muted cursor-pointer hover:text-content" on:click={() => toggleSort("jurisdiction")}>
                Jurisdiction {sortIcon("jurisdiction")}
              </th>
              <th class="px-3 py-3 text-left font-medium text-content-muted text-center">Cands</th>
              <th class="px-3 py-3 text-left font-medium text-content-muted cursor-pointer hover:text-content whitespace-nowrap" on:click={() => toggleSort("draft_updated_at")}>
                Updated {sortIcon("draft_updated_at")}
              </th>
              <th class="px-3 py-3 text-left font-medium text-content-muted whitespace-nowrap">Freshness</th>
              <th class="px-3 py-3 text-left font-medium text-content-muted cursor-pointer hover:text-content whitespace-nowrap" on:click={() => toggleSort("status")}>
                Status {sortIcon("status")}
              </th>
              <th class="px-3 py-3 text-left font-medium text-content-muted cursor-pointer hover:text-content whitespace-nowrap" on:click={() => toggleSort("total_runs")}>
                Runs {sortIcon("total_runs")}
              </th>
              <th class="px-3 py-3 text-left font-medium text-content-muted cursor-pointer hover:text-content whitespace-nowrap" on:click={() => toggleSort("quality_score")}>
                Quality {sortIcon("quality_score")}
              </th>
              <th class="px-3 py-3 text-left font-medium text-content-muted">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-stroke">
            {#each filteredRows as row (row.race_id)}
              <tr
                class="hover:bg-surface-alt cursor-pointer {selected.has(row.race_id) ? 'bg-blue-50 dark:bg-blue-900/20' : hasPendingDraft(row) ? 'bg-amber-50/40 dark:bg-amber-900/10' : ''}"
                on:click={() => onSelectRace(row)}
              >
                <td class="pl-4 pr-2 py-3" on:click|stopPropagation>
                  <input
                    type="checkbox"
                    checked={selected.has(row.race_id)}
                    on:change={() => toggleSelect(row.race_id)}
                    class="rounded border-stroke"
                  />
                </td>
                <td class="px-3 py-3 font-mono text-xs text-content whitespace-nowrap">
                  <span>{row.race_id}</span>
                  {#if row.status === "running"}
                    <span class="ml-1.5 inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200">
                      <svg class="animate-spin h-2.5 w-2.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                        <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      running
                    </span>
                  {:else if row.status === "queued"}
                    <span class="ml-1.5 inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-200">
                      queued
                    </span>
                  {/if}
                </td>
                <td class="px-3 py-3 text-content max-w-40 truncate" title={row.title ?? ""}>{row.title ?? "—"}</td>
                <td class="px-3 py-3 text-content-muted max-w-32 truncate">{row.jurisdiction ?? "—"}</td>
                <td class="px-3 py-3 text-content-muted text-center font-mono">{row.candidate_count || "—"}</td>
                <td class="px-3 py-3 text-content-muted whitespace-nowrap">{formatDate(row.draft_updated_at)}</td>
                <td class="px-3 py-3">
                  {#if row.freshness}
                    <span class="px-2 py-0.5 rounded-full text-xs font-medium {freshnessBadgeClass(row.freshness)}">{row.freshness}</span>
                  {:else}
                    <span class="text-content-faint">—</span>
                  {/if}
                </td>
                <td class="px-3 py-3">
                  <div class="flex items-center gap-1.5">
                    <span class="px-2 py-0.5 rounded-full text-xs font-medium {statusBadgeClass(row.status)}">
                      {row.status}
                    </span>
                    {#if hasPendingDraft(row)}
                      <span
                        class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-200 border border-amber-300 dark:border-amber-700"
                        title="Draft available — newer than published version"
                      >
                        <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                        </svg>
                        draft
                      </span>
                    {/if}
                  </div>
                </td>
                <td class="px-3 py-3 text-content-muted text-center font-mono">{row.total_runs}</td>
                <td class="px-3 py-3">
                  {#if row.quality_score != null}
                    <QualityBadge score={row.quality_score} />
                  {:else}
                    <span class="text-content-faint">—</span>
                  {/if}
                </td>
                <td class="px-3 py-3" on:click|stopPropagation>
                  <div class="flex items-center space-x-1">
                    {#if hasPendingDraft(row)}
                      <button
                        type="button"
                        class="px-2 py-1 text-xs border border-green-300 dark:border-green-700 rounded text-green-700 dark:text-green-300 hover:bg-green-50 dark:hover:bg-green-900/20 disabled:opacity-40 font-medium"
                        disabled={publishing.has(row.race_id)}
                        on:click={() => handlePublish(row.race_id)}
                      >
                        {publishing.has(row.race_id) ? "…" : "Publish"}
                      </button>
                    {/if}
                    {#if row.status === "published"}
                      <button
                        type="button"
                        class="px-2 py-1 text-xs border border-amber-300 dark:border-amber-700 rounded text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-900/20 disabled:opacity-40"
                        disabled={publishing.has(row.race_id)}
                        on:click={() => handleUnpublish(row.race_id)}
                      >
                        Unpublish
                      </button>
                    {/if}
                    <button
                      type="button"
                      class="px-2 py-1 text-xs border border-stroke rounded text-content-muted hover:bg-surface-alt"
                      on:click={() => handlePreview(row.race_id)}
                    >
                      View
                    </button>
                    {#if row.status !== "running" && row.status !== "queued"}
                      <button
                        type="button"
                        class="px-2 py-1 text-xs border border-red-200 dark:border-red-900 rounded text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                        on:click={() => handleDelete(row.race_id)}
                      >
                        Delete
                      </button>
                    {/if}
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <div class="px-4 py-2 bg-surface-alt border-t border-stroke text-xs text-content-subtle flex items-center justify-between">
        <span>
          {filteredRows.length} race{filteredRows.length !== 1 ? "s" : ""}
          {#if search} matching "{search}"{/if}
          {#if statusFilter !== "all"} · filtered by {statusFilter}{/if}
        </span>
        <span>
          {rows.filter((r) => r.status === "published").length} published ·
          {rows.filter((r) => r.status === "draft").length} draft ·
          {rows.filter((r) => r.status === "queued" || r.status === "running").length} active
        </span>
      </div>
    </div>
  {/if}
</div>
