<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import {
    daysUntilElection,
    formatElectionDate,
  } from "$lib/utils/electionDate";

  export let electionDate: string;

  let days = 0;
  let status: "upcoming" | "today" | "past" = "upcoming";
  let intervalId: ReturnType<typeof setInterval> | null = null;

  function updateCountdown() {
    const difference = daysUntilElection(electionDate);
    if (difference === null) return;

    if (difference === 0) {
      status = "today";
      days = 0;
    } else if (difference < 0) {
      status = "past";
      days = 0;
    } else {
      status = "upcoming";
      days = difference;
    }
  }

  onMount(() => {
    updateCountdown();
    intervalId = setInterval(updateCountdown, 60 * 60 * 1000);
  });

  onDestroy(() => {
    if (intervalId) clearInterval(intervalId);
  });
</script>

<div
  class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-stroke bg-surface-alt/40 px-4 py-2.5 text-sm"
>
  <span class="font-bold text-content">
    {#if status === "upcoming"}
      {days} day{days === 1 ? "" : "s"} until Election Day
    {:else if status === "today"}
      Election Day is today
    {:else}
      Election completed
    {/if}
  </span>
  <span class="text-content-muted">
    {formatElectionDate(electionDate)}
  </span>
</div>
