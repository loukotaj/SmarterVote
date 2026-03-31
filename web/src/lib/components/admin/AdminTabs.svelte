<script lang="ts">
  export let activeTab: "dashboard" | "races" | "pipeline" = "dashboard";
  export let alertCount: number = 0;

  const tabs = [
    { id: "dashboard", label: "Dashboard" },
    { id: "races", label: "Races" },
    { id: "pipeline", label: "Pipeline" },
  ] as const;
</script>

<div class="border-b border-gray-200 mb-6">
  <nav class="-mb-px flex space-x-1" aria-label="Admin tabs">
    {#each tabs as tab}
      <button
        type="button"
        class="relative px-5 py-3 text-sm font-medium transition-colors rounded-t-lg focus:outline-none
          {activeTab === tab.id
            ? 'border-b-2 border-blue-600 text-blue-700 bg-blue-50'
            : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'}"
        on:click={() => (activeTab = tab.id)}
        aria-selected={activeTab === tab.id}
        role="tab"
      >
        {tab.label}
        {#if tab.id === "dashboard" && alertCount > 0}
          <span
            class="ml-1.5 inline-flex items-center justify-center w-5 h-5 text-xs font-bold rounded-full
              {alertCount > 0 ? 'bg-red-500 text-white' : 'bg-gray-200 text-gray-600'}"
          >
            {alertCount > 99 ? "99+" : alertCount}
          </span>
        {/if}
      </button>
    {/each}
  </nav>
</div>
