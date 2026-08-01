<script lang="ts">
  import { browser } from "$app/environment";

  export let activeTab: "dashboard" | "races" | "runs" | "forecasts" | "costs" =
    "dashboard";

  const tabs = [
    { id: "dashboard", label: "Dashboard" },
    { id: "races", label: "Races" },
    { id: "runs", label: "Runs" },
    { id: "forecasts", label: "Forecasts" },
    { id: "costs", label: "Costs" },
  ] as const;

  type TabId = (typeof tabs)[number]["id"];
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

<div class="border-b border-stroke mb-6">
  <nav class="-mb-px flex space-x-1" aria-label="Admin tabs">
    {#each tabs as tab}
      <button
        type="button"
        class="relative px-5 py-3 text-sm font-medium transition-colors rounded-t-lg focus:outline-none
          {activeTab === tab.id
          ? 'border-b-2 border-blue-600 dark:border-blue-400 text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/20'
          : 'text-content-subtle hover:text-content-muted hover:bg-surface-alt'}"
        on:click={() => selectTab(tab.id)}
        aria-selected={activeTab === tab.id}
        role="tab"
      >
        {tab.label}
      </button>
    {/each}
  </nav>
</div>
