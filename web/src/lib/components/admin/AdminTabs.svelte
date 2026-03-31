<script lang="ts">
  import { browser } from "$app/environment";

  export let activeTab: "dashboard" | "races" | "pipeline" = "dashboard";
  export let alertCount: number = 0;

  const tabs = [
    { id: "dashboard", label: "Dashboard" },
    { id: "races", label: "Races" },
    { id: "pipeline", label: "Pipeline" },
  ] as const;

  type TabId = typeof tabs[number]["id"];
  const VALID_TABS = new Set<string>(tabs.map((t) => t.id));

  function selectTab(id: TabId) {
    activeTab = id;
    if (browser) {
      const url = new URL(window.location.href);
      if (id === "dashboard") {
        url.searchParams.delete("tab");
      } else {
        url.searchParams.set("tab", id);
      }
      history.replaceState(history.state, "", url);
    }
  }

  // Read tab from URL on init
  if (browser) {
    const param = new URLSearchParams(window.location.search).get("tab");
    if (param && VALID_TABS.has(param)) {
      activeTab = param as TabId;
    }
  }
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
        on:click={() => selectTab(tab.id)}
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
