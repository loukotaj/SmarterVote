<script lang="ts">
  import TabButton from "$lib/components/TabButton.svelte";
  import type { ForecastTab } from "$lib/utils/forecast";

  export let tabs: { id: ForecastTab; label: string }[];
  export let activeTab: ForecastTab;
  export let onSelect: (tab: ForecastTab) => void;
</script>

<div class="border-b border-stroke/60 flex gap-1 overflow-x-auto">
  {#each tabs as tab}
    <TabButton active={activeTab === tab.id} onClick={() => onSelect(tab.id)}>
      {tab.label}
    </TabButton>
  {/each}
</div>
