<script lang="ts">
  import { onMount } from "svelte";
  import { analyticsService } from "$lib/services/analyticsService";
  import { PipelineApiService } from "$lib/services/pipelineApiService";
  import QualityBadge from "./QualityBadge.svelte";
  import type { PublishedRaceSummary } from "$lib/services/pipelineApiService";
  import type { RaceAnalytics } from "$lib/types";

  export let onUpdateRace: (raceId: string) => void = () => {};

  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";

  interface RaceRow {
    race_id: string;
    title?: string;
    office?: string;
    jurisdiction?: string;
    candidates: string[];
    updated_utc?: string;
    requests_24h: number;
    last_accessed?: string;
    quality_score: number;
    age_days: number;
    freshness: "fresh" | "recent" | "aging" | "stale";
  }

  let rows: RaceRow[] = [];
  let filteredRows: RaceRow[] = [];
  let loading = true;
  let error = "";
  let search = "";
  let sortKey: keyof RaceRow = "requests_24h";
  let sortAsc = false;
  let selected = new Set<string>();
  let bulkUpdating = false;

  function computeQuality(race: PublishedRaceSummary): number {
    // Based on candidate count as a proxy (full data not available in summary)
    // 0-100: more candidates = higher potential, presence alone = 50 baseline
    const candidateScore = Math.min(race.candidates.length * 10, 30);
    return 50 + candidateScore;
  }

  function computeFreshness(agedays: number): "fresh" | "recent" | "aging" | "stale" {
    if (agedays <= 7) return "fresh";
    if (agedays <= 14) return "recent";
    if (agedays <= 30) return "aging";
    return "stale";
  }

  function computeAgeDays(updated_utc?: string): number {
    if (!updated_utc) return 999;
    const diff = Date.now() - new Date(updated_utc).getTime();
    return Math.floor(diff / 86_400_000);
  }

  async function loadData() {
    try {
      error = "";
      const apiService = new PipelineApiService(API_BASE);
      const [racesResult, analyticsResult] = await Promise.allSettled([
        apiService.loadPublishedRaces(),
        analyticsService.getRaces(24),
      ]);

      const races: PublishedRaceSummary[] = racesResult.status === "fulfilled" ? racesResult.value : [];
      const analyticsRaces: RaceAnalytics[] =
        analyticsResult.status === "fulfilled" ? analyticsResult.value.races : [];

      const analyticsMap = new Map<string, RaceAnalytics>(analyticsRaces.map((r) => [r.race_id, r]));

      rows = races.map((r) => {
        const a = analyticsMap.get(r.id);
        const age_days = computeAgeDays(r.updated_utc);
        return {
          race_id: r.id,
          title: r.title,
          office: r.office,
          jurisdiction: r.jurisdiction,
          candidates: r.candidates.map((c) => c.name),
          updated_utc: r.updated_utc,
          requests_24h: a?.requests_24h ?? 0,
          last_accessed: a?.last_accessed,
          quality_score: computeQuality(r),
          age_days,
          freshness: computeFreshness(age_days),
        };
      });

      applyFilterSort();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  function applyFilterSort() {
    let result = rows.filter((r) => {
      if (!search) return true;
      const s = search.toLowerCase();
      return r.race_id.includes(s) || (r.jurisdiction ?? "").toLowerCase().includes(s) || (r.title ?? "").toLowerCase().includes(s);
    });

    result.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === undefined) return 1;
      if (bv === undefined) return -1;
      if (typeof av === "number" && typeof bv === "number") return sortAsc ? av - bv : bv - av;
      return sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });

    filteredRows = result;
  }

  $: if (rows) applyFilterSort();
  $: if (search !== undefined) applyFilterSort();

  function toggleSort(key: keyof RaceRow) {
    if (sortKey === key) {
      sortAsc = !sortAsc;
    } else {
      sortKey = key;
      sortAsc = false;
    }
  }

  function toggleSelect(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    selected = next;
  }

  function toggleAll() {
    if (selected.size === filteredRows.length) {
      selected = new Set();
    } else {
      selected = new Set(filteredRows.map((r) => r.race_id));
    }
  }

  async function handleBulkUpdate() {
    if (!selected.size) return;
    bulkUpdating = true;
    for (const race_id of selected) {
      onUpdateRace(race_id);
    }
    selected = new Set();
    bulkUpdating = false;
  }

  function freshnessBadgeClass(f: string) {
    switch (f) {
      case "fresh":
        return "bg-green-100 text-green-800";
      case "recent":
        return "bg-yellow-100 text-yellow-800";
      case "aging":
        return "bg-orange-100 text-orange-800";
      case "stale":
        return "bg-red-100 text-red-800";
      default:
        return "bg-gray-100 text-gray-600";
    }
  }

  function formatDate(s?: string) {
    if (!s) return "—";
    return new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function sortIcon(key: keyof RaceRow) {
    if (sortKey !== key) return "↕";
    return sortAsc ? "↑" : "↓";
  }

  onMount(loadData);
</script>

<div class="space-y-4">
  <!-- Toolbar -->
  <div class="flex items-center justify-between gap-3 flex-wrap">
    <div class="flex-1 min-w-48">
      <input
        type="search"
        bind:value={search}
        placeholder="Search by race ID, jurisdiction…"
        class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
      />
    </div>
    <div class="flex items-center space-x-2">
      {#if selected.size > 0}
        <button
          type="button"
          class="btn-primary px-4 py-2 text-sm rounded-lg disabled:opacity-40"
          disabled={bulkUpdating}
          on:click={handleBulkUpdate}
        >
          {bulkUpdating ? "Queuing…" : `Update ${selected.size} Selected`}
        </button>
      {/if}
      <button
        type="button"
        class="px-3 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 text-gray-700"
        on:click={loadData}
      >
        Refresh
      </button>
    </div>
  </div>

  {#if error}
    <div class="card p-4 text-sm text-red-600">{error}</div>
  {:else if loading}
    <div class="card p-8 text-center text-gray-400 text-sm">Loading races…</div>
  {:else if filteredRows.length === 0}
    <div class="card p-8 text-center text-gray-400 text-sm">No races found</div>
  {:else}
    <div class="card overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="bg-gray-50 border-b border-gray-200">
            <tr>
              <th class="pl-4 pr-2 py-3 text-left">
                <input
                  type="checkbox"
                  checked={selected.size === filteredRows.length && filteredRows.length > 0}
                  indeterminate={selected.size > 0 && selected.size < filteredRows.length}
                  on:change={toggleAll}
                  class="rounded border-gray-300"
                />
              </th>
              <th class="px-3 py-3 text-left font-medium text-gray-600 cursor-pointer hover:text-gray-900 whitespace-nowrap" on:click={() => toggleSort("race_id")}>
                Race ID {sortIcon("race_id")}
              </th>
              <th class="px-3 py-3 text-left font-medium text-gray-600 cursor-pointer hover:text-gray-900" on:click={() => toggleSort("jurisdiction")}>
                Jurisdiction {sortIcon("jurisdiction")}
              </th>
              <th class="px-3 py-3 text-left font-medium text-gray-600">Candidates</th>
              <th class="px-3 py-3 text-left font-medium text-gray-600 cursor-pointer hover:text-gray-900 whitespace-nowrap" on:click={() => toggleSort("age_days")}>
                Updated {sortIcon("age_days")}
              </th>
              <th class="px-3 py-3 text-left font-medium text-gray-600 whitespace-nowrap">Freshness</th>
              <th class="px-3 py-3 text-left font-medium text-gray-600 cursor-pointer hover:text-gray-900 whitespace-nowrap" on:click={() => toggleSort("requests_24h")}>
                Reqs 24h {sortIcon("requests_24h")}
              </th>
              <th class="px-3 py-3 text-left font-medium text-gray-600 cursor-pointer hover:text-gray-900 whitespace-nowrap" on:click={() => toggleSort("quality_score")}>
                Quality {sortIcon("quality_score")}
              </th>
              <th class="px-3 py-3 text-left font-medium text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            {#each filteredRows as row (row.race_id)}
              <tr class="hover:bg-gray-50 {selected.has(row.race_id) ? 'bg-blue-50' : ''}">
                <td class="pl-4 pr-2 py-3">
                  <input
                    type="checkbox"
                    checked={selected.has(row.race_id)}
                    on:change={() => toggleSelect(row.race_id)}
                    class="rounded border-gray-300"
                  />
                </td>
                <td class="px-3 py-3 font-mono text-xs text-gray-800 whitespace-nowrap">{row.race_id}</td>
                <td class="px-3 py-3 text-gray-700 max-w-32 truncate">{row.jurisdiction ?? "—"}</td>
                <td class="px-3 py-3 text-gray-600 max-w-40">
                  <span class="truncate block" title={row.candidates.join(", ")}>{row.candidates.join(", ") || "—"}</span>
                </td>
                <td class="px-3 py-3 text-gray-600 whitespace-nowrap">{formatDate(row.updated_utc)}</td>
                <td class="px-3 py-3">
                  <span class="px-2 py-0.5 rounded-full text-xs font-medium {freshnessBadgeClass(row.freshness)}">
                    {row.freshness}
                  </span>
                </td>
                <td class="px-3 py-3 text-gray-700 text-right font-mono">{row.requests_24h}</td>
                <td class="px-3 py-3">
                  <QualityBadge score={row.quality_score} />
                </td>
                <td class="px-3 py-3">
                  <div class="flex items-center space-x-1">
                    <button
                      type="button"
                      class="px-2 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50"
                      on:click={() => onUpdateRace(row.race_id)}
                    >
                      Update
                    </button>
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <div class="px-4 py-2 bg-gray-50 border-t border-gray-200 text-xs text-gray-500">
        {filteredRows.length} race{filteredRows.length !== 1 ? "s" : ""}
        {#if search} matching "{search}"{/if}
      </div>
    </div>
  {/if}
</div>
