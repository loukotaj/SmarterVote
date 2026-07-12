<script lang="ts">
  import ElectionDirectory from "$lib/components/ElectionDirectory.svelte";
  import type { PageData } from "./$types";

  export let data: PageData;
</script>

<svelte:head>
  <title>National Election Guides | Smarter.Vote</title>
  <meta
    name="description"
    content="Browse sourced, nonpartisan candidate research for national elections."
  />
  <link rel="canonical" href="https://smarter.vote/elections/" />
</svelte:head>

<ElectionDirectory races={data.races ?? []} />
