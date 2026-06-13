<script lang="ts">
  import { onMount } from "svelte";
  import { writable } from "svelte/store";
  import {
    createSvelteTable,
    getCoreRowModel,
    getFilteredRowModel,
    getSortedRowModel,
  } from "@tanstack/svelte-table";
  import type {
    ColumnDef,
    ColumnFiltersState,
    FilterFn,
    SortingFn,
    SortingState,
    TableOptions,
    Updater,
  } from "@tanstack/svelte-table";
  import { PipelineApiService } from "$lib/services/pipelineApiService";
  import type { RaceRecord, RaceStatusType } from "$lib/types";

  const API_BASE = import.meta.env.VITE_RACES_API_URL || "http://127.0.0.1:8080";
  const apiService = new PipelineApiService(API_BASE);

  let rows: RaceRecord[] = [];
  let loading = true;
  let error = "";
  let globalFilter = "";
  let statusFilter: RaceStatusType | "all" = "all";
  let sorting: SortingState = [{ id: "draft_updated_at", desc: true }];
  let columnFilters: ColumnFiltersState = [];

  export async function refresh() {
    loading = true;
    await loadData();
  }

  function hasDraft(row: RaceRecord): boolean {
    if (typeof row.draft_exists === "boolean") return row.draft_exists;
    return row.status === "draft" || !!row.draft_updated_at;
  }

  function hasPublished(row: RaceRecord): boolean {
    if (typeof row.published_exists === "boolean") return row.published_exists;
    return row.status === "published" || !!row.published_at;
  }

  function hasPendingDraft(row: RaceRecord): boolean {
    if (!hasDraft(row)) return false;
    if (!hasPublished(row)) return true;
    if (!row.draft_updated_at || !row.published_at) return true;
    return row.draft_updated_at > row.published_at;
  }

  function isDiscoveryOnly(row: RaceRecord): boolean {
    const opts = (row.last_run_options ?? row.queue_options) as { enabled_steps?: string[] } | undefined;
    if (!opts) return false;
    const steps = opts.enabled_steps;
    return Array.isArray(steps) && steps.length === 1 && steps[0] === "discovery";
  }

  function draftTimestamp(row: RaceRecord): string {
    return hasDraft(row) ? row.draft_updated_at ?? "" : "";
  }

  function qualityValue(row: RaceRecord): number {
    const grades: Record<string, number> = { A: 95, B: 85, C: 75, D: 65, F: 55 };
    return row.quality_grade ? grades[row.quality_grade] : -1;
  }

  function normalize(value: unknown): string {
    return String(value ?? "").trim().toLowerCase();
  }

  const textFilter: FilterFn<RaceRecord> = (row, columnId, value) => {
    const needle = normalize(value);
    if (!needle) return true;
    return normalize(row.getValue(columnId)).includes(needle);
  };

  const statusExactFilter: FilterFn<RaceRecord> = (row, columnId, value) => {
    const filter = normalize(value);
    return !filter || filter === "all" || normalize(row.getValue(columnId)) === filter;
  };

  const globalRaceFilter: FilterFn<RaceRecord> = (row, _columnId, value) => {
    const needle = normalize(value);
    if (!needle) return true;
    const race = row.original;
    return [
      race.race_id,
      race.title,
      race.office,
      race.jurisdiction,
      race.status,
      race.quality_grade,
      race.candidate_count,
      race.total_runs,
    ].some((item) => normalize(item).includes(needle));
  };

  const dateSort: SortingFn<RaceRecord> = (a, b, columnId) => {
    const av = Date.parse(String(a.getValue(columnId) || ""));
    const bv = Date.parse(String(b.getValue(columnId) || ""));
    if (Number.isNaN(av) && Number.isNaN(bv)) return 0;
    if (Number.isNaN(av)) return -1;
    if (Number.isNaN(bv)) return 1;
    return av - bv;
  };

  const columns: ColumnDef<RaceRecord>[] = [
    {
      accessorKey: "race_id",
      header: "Race ID",
      filterFn: textFilter,
      sortingFn: "alphanumeric",
    },
    {
      accessorKey: "title",
      header: "Title",
      filterFn: textFilter,
      sortingFn: "alphanumeric",
    },
    {
      accessorKey: "jurisdiction",
      header: "Jurisdiction",
      filterFn: textFilter,
      sortingFn: "alphanumeric",
    },
    {
      accessorKey: "candidate_count",
      header: "Cands",
      filterFn: textFilter,
      sortingFn: "basic",
    },
    {
      id: "draft_updated_at",
      header: "Updated",
      accessorFn: draftTimestamp,
      filterFn: textFilter,
      sortingFn: dateSort,
      sortUndefined: "last",
    },
    {
      accessorKey: "status",
      header: "Status",
      filterFn: statusExactFilter,
      sortingFn: "alphanumeric",
    },
    {
      accessorKey: "total_runs",
      header: "Runs",
      filterFn: textFilter,
      sortingFn: "basic",
    },
    {
      id: "quality",
      header: "Quality",
      accessorFn: qualityValue,
      filterFn: (row, _columnId, value) => {
        const needle = normalize(value);
        if (!needle) return true;
        return normalize(row.original.quality_grade).includes(needle);
      },
      sortingFn: "basic",
    },
    {
      id: "actions",
      header: "Preview",
      enableSorting: false,
      enableColumnFilter: false,
    },
  ];

  const options = writable<TableOptions<RaceRecord>>({
    data: rows,
    columns,
    state: {
      sorting,
      columnFilters,
      globalFilter,
    },
    filterFns: {
      text: textFilter,
      statusExact: statusExactFilter,
      globalRace: globalRaceFilter,
    },
    globalFilterFn: globalRaceFilter,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const table = createSvelteTable(options);

  $: filteredCount = $table.getFilteredRowModel().rows.length;

  function updateTableState() {
    options.update((old) => ({
      ...old,
      data: rows,
      state: {
        ...old.state,
        sorting,
        columnFilters,
        globalFilter,
      },
    }));
  }

  function resolveUpdater<T>(updater: Updater<T>, current: T): T {
    return updater instanceof Function ? updater(current) : updater;
  }

  function setSorting(updater: Updater<SortingState>) {
    sorting = resolveUpdater(updater, sorting);
    updateTableState();
  }

  function setColumnFilters(updater: Updater<ColumnFiltersState>) {
    columnFilters = resolveUpdater(updater, columnFilters);
    statusFilter = (columnFilters.find((filter) => filter.id === "status")?.value as RaceStatusType | undefined) ?? "all";
    updateTableState();
  }

  function setGlobalFilter(updater: Updater<string>) {
    globalFilter = resolveUpdater(updater, globalFilter);
    updateTableState();
  }

  async function loadData() {
    try {
      error = "";
      rows = await apiService.listRaces();
      updateTableState();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  function previewUrl(row: RaceRecord): string | null {
    if (hasDraft(row)) return `/races/${row.race_id}?draft=true`;
    if (hasPublished(row)) return `/races/${row.race_id}`;
    return null;
  }

  function handlePreview(row: RaceRecord) {
    const url = previewUrl(row);
    if (url) window.open(url, "_blank");
  }

  function handleGlobalFilterInput(event: Event) {
    $table.setGlobalFilter((event.currentTarget as HTMLInputElement).value);
  }

  function handleStatusFilter(event: Event) {
    const value = (event.currentTarget as HTMLSelectElement).value as RaceStatusType | "all";
    statusFilter = value;
    $table.getColumn("status")?.setFilterValue(value === "all" ? "" : value);
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

  function gradeBadgeClass(g: string) {
    switch (g) {
      case "A": return "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 border-green-200";
      case "B": return "bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200 border-yellow-200";
      case "C": return "bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200 border-orange-200";
      case "D": return "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 border-red-200";
      case "F": return "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 border-red-200";
      default: return "bg-surface-alt text-content-muted border-stroke";
    }
  }

  function formatDate(s?: string) {
    if (!s) return "-";
    return new Date(s).toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  const STATUS_OPTIONS: { value: RaceStatusType | "all"; label: string }[] = [
    { value: "all", label: "All Statuses" },
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
  <!-- Toolbar -->
  <div class="flex items-center justify-between gap-3 flex-wrap">
    <div class="flex items-center gap-2 flex-1 min-w-0">
      <input
        type="search"
        value={globalFilter}
        on:input={handleGlobalFilterInput}
        placeholder="Search visible races..."
        class="flex-1 max-w-md px-3 py-2 text-sm border border-stroke rounded-lg bg-surface text-content focus:outline-none focus:border-blue-500"
      />
      <select
        value={statusFilter}
        on:change={handleStatusFilter}
        class="px-3 py-2 text-sm border border-stroke rounded-lg bg-surface text-content focus:outline-none focus:border-blue-500"
        aria-label="Filter by status"
      >
        {#each STATUS_OPTIONS as opt}
          <option value={opt.value}>{opt.label}</option>
        {/each}
      </select>
    </div>
    <div class="flex items-center space-x-2">
      <button
        type="button"
        class="px-4 py-2 text-sm border border-stroke rounded-lg hover:bg-surface-alt text-content transition-colors font-medium"
        on:click={loadData}
      >
        Refresh
      </button>
    </div>
  </div>

  {#if error}
    <div class="card p-4 text-sm text-red-600">{error}</div>
  {:else if loading}
    <div class="card p-8 text-center text-content-faint text-sm">Loading races...</div>
  {:else if filteredCount === 0}
    <div class="card p-8 text-center text-content-faint text-sm">No races found</div>
  {:else}
    <div class="card overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="bg-surface-alt border-b border-stroke">
            <tr>
              {#each $table.getHeaderGroups()[0].headers as header}
                <th class="px-4 py-3 text-left font-semibold text-content-muted align-middle whitespace-nowrap">
                  {#if !header.isPlaceholder}
                    <button
                      type="button"
                      class="group inline-flex items-center gap-1 text-left hover:text-content disabled:cursor-default disabled:hover:text-content-muted"
                      disabled={!header.column.getCanSort()}
                      on:click={header.column.getToggleSortingHandler()}
                    >
                      <span>{header.column.columnDef.header}</span>
                      {#if header.column.getCanSort()}
                        <span class="inline-flex h-4 w-4 items-center justify-center text-content-faint group-hover:text-content-muted" aria-hidden="true">
                          {#if header.column.getIsSorted() === "asc"}
                            <svg viewBox="0 0 16 16" class="h-3 w-3" fill="currentColor"><path d="M8 3 3.5 9h9L8 3z" /></svg>
                          {:else if header.column.getIsSorted() === "desc"}
                            <svg viewBox="0 0 16 16" class="h-3 w-3" fill="currentColor"><path d="M8 13 3.5 7h9L8 13z" /></svg>
                          {:else}
                            <svg viewBox="0 0 16 16" class="h-3 w-3 opacity-60" fill="currentColor"><path d="M8 2.5 4.5 7h7L8 2.5zM8 13.5 4.5 9h7L8 13.5z" /></svg>
                          {/if}
                        </span>
                      {/if}
                    </button>
                  {/if}
                </th>
              {/each}
            </tr>
          </thead>
          <tbody class="divide-y divide-stroke bg-surface">
            {#each $table.getRowModel().rows as tableRow (tableRow.id)}
              {@const row = tableRow.original}
              <tr class="hover:bg-surface-alt transition-colors {hasPendingDraft(row) ? 'bg-amber-50/20 dark:bg-amber-900/5' : ''}">
                <td class="px-4 py-3.5 font-mono text-xs text-content whitespace-nowrap align-middle">
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
                <td class="px-4 py-3.5 text-content max-w-xs truncate align-middle" title={row.title ?? ""}>{row.title ?? "-"}</td>
                <td class="px-4 py-3.5 text-content-muted max-w-[150px] truncate align-middle">{row.jurisdiction ?? "-"}</td>
                <td class="px-4 py-3.5 text-content-muted font-mono align-middle">{row.candidate_count || "-"}</td>
                <td class="px-4 py-3.5 text-content-muted whitespace-nowrap align-middle">{hasDraft(row) ? formatDate(row.draft_updated_at) : "-"}</td>
                <td class="px-4 py-3.5 align-middle">
                  <div class="flex items-center gap-1.5">
                    <span class="px-2 py-0.5 rounded-full text-xs font-medium {statusBadgeClass(row.status)}">
                      {row.status}
                    </span>
                    {#if isDiscoveryOnly(row)}
                      <span
                        class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-xs font-semibold bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300 border border-violet-300 dark:border-violet-700"
                        title="Last run was discovery-only - candidates found but issues/research/finance not yet populated"
                      >
                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
                          <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                        </svg>
                        discovery
                      </span>
                    {/if}
                    {#if hasDraft(row)}
                      <span
                        class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-200 border border-amber-300 dark:border-amber-700"
                        title={hasPublished(row) ? "Draft available" : "Unpublished draft available"}
                      >
                        <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                        </svg>
                        draft
                      </span>
                    {/if}
                  </div>
                </td>
                <td class="px-4 py-3.5 text-content-muted font-mono align-middle">{row.total_runs}</td>
                <td class="px-4 py-3.5 align-middle">
                  {#if row.quality_grade}
                    <span class="inline-flex items-center px-2 py-0.5 text-xs font-semibold rounded-full border {gradeBadgeClass(row.quality_grade)}">
                      {row.quality_grade}
                    </span>
                  {:else}
                    <span class="text-content-faint">-</span>
                  {/if}
                </td>
                <td class="px-4 py-3.5 align-middle" on:click|stopPropagation>
                  <button
                    type="button"
                    class="px-2.5 py-1 text-xs border border-stroke rounded text-content hover:bg-surface-alt disabled:opacity-40 transition-colors font-medium whitespace-nowrap"
                    disabled={!previewUrl(row)}
                    title={hasDraft(row) ? "Open draft preview" : hasPublished(row) ? "Open published page" : "No draft or published page exists"}
                    on:click={() => handlePreview(row)}
                  >
                    {hasDraft(row) ? "View Draft" : "View Page"}
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <div class="px-4 py-2 bg-surface-alt border-t border-stroke text-xs text-content-subtle flex items-center justify-between">
        <span>
          {filteredCount} race{filteredCount !== 1 ? "s" : ""}
          {#if globalFilter} matching "{globalFilter}"{/if}
          {#if statusFilter !== "all"} · filtered by {statusFilter}{/if}
        </span>
        <span>
          {rows.filter((r) => r.status === "published").length} published ·
          {rows.filter((r) => r.status === "draft").length} draft ·
          {rows.filter((r) => r.status === "queued" || r.status === "running").length} active
          {#if rows.filter(isDiscoveryOnly).length > 0}
            · <span class="text-violet-600 dark:text-violet-400">{rows.filter(isDiscoveryOnly).length} discovery-only</span>
          {/if}
        </span>
      </div>
    </div>
  {/if}
</div>
