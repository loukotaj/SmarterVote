<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import type { Artifact } from "$lib/types";

  export let artifacts: Artifact[] = [];
  export let isRefreshing = false;

  const dispatch = createEventDispatcher<{
    "artifact-click": Artifact;
    refresh: void;
  }>();

  function handleArtifactClick(artifact: Artifact) {
    dispatch("artifact-click", artifact);
  }

  function handleRefresh() {
    dispatch("refresh");
  }
</script>

<div class="card p-0">
  <div class="p-4 border-b border-stroke flex items-center justify-between">
    <h3 class="text-lg font-semibold text-content">Artifacts</h3>
    <button
      on:click={handleRefresh}
      disabled={isRefreshing}
      class="text-sm text-blue-600 hover:text-blue-500 disabled:text-content-faint flex items-center space-x-1"
    >
      {#if isRefreshing}
        <svg
          class="animate-spin h-3 w-3"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            class="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            stroke-width="4"
          />
          <path
            class="opacity-75"
            fill="currentColor"
            d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      {/if}
      <span>Refresh</span>
    </button>
  </div>

  <ul class="artifacts-list custom-scrollbar">
    {#each artifacts as artifact}
      <li>
        <button
          type="button"
          class="cursor-pointer w-full flex justify-between items-center px-0 py-0 bg-transparent border-none text-inherit"
          on:click={() => handleArtifactClick(artifact)}
        >
          <span class="font-mono text-sm">{artifact.id}</span>
          <span class="text-xs text-content-subtle">
            {artifact.size ? `${(artifact.size / 1024).toFixed(1)} KB` : "—"}
          </span>
        </button>
      </li>
    {:else}
      <li class="text-center text-content-subtle text-sm py-4">No artifacts yet</li>
    {/each}
  </ul>
</div>

<style>
  .artifacts-list {
    list-style: none;
    padding: 0;
    max-height: 200px;
    overflow-y: auto;
  }

  .artifacts-list li {
    font-size: 0.875rem;
    padding: 8px 12px;
    border-bottom: 1px solid rgb(var(--sv-border));
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .artifacts-list li:hover {
    background-color: rgb(var(--sv-surface-alt));
  }

  .custom-scrollbar::-webkit-scrollbar {
    width: 6px;
  }

  .custom-scrollbar::-webkit-scrollbar-track {
    background: rgb(var(--sv-surface-alt));
    border-radius: 3px;
  }

  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgb(var(--sv-border));
    border-radius: 3px;
  }

  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: rgb(var(--sv-text-faint));
  }
</style>
