<script lang="ts">
  import { onMount, onDestroy } from "svelte";

  export let electionDate: string;

  let days = 0;
  let hours = 0;
  let minutes = 0;
  let seconds = 0;
  let status: "upcoming" | "today" | "past" = "upcoming";
  let intervalId: any;

  function updateCountdown() {
    if (!electionDate) return;
    const target = new Date(electionDate).getTime();
    const now = new Date().getTime();
    const difference = target - now;

    if (difference <= 0) {
      const targetDate = new Date(electionDate);
      const isTodayStr = targetDate.toDateString() === new Date().toDateString();
      if (isTodayStr) {
        status = "today";
      } else {
        status = "past";
      }
      if (intervalId) clearInterval(intervalId);
      return;
    }

    status = "upcoming";
    days = Math.floor(difference / (1000 * 60 * 60 * 24));
    hours = Math.floor((difference % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    minutes = Math.floor((difference % (1000 * 60 * 60)) / (1000 * 60));
    seconds = Math.floor((difference % (1000 * 60)) / 1000);
  }

  onMount(() => {
    updateCountdown();
    intervalId = setInterval(updateCountdown, 1000);
  });

  onDestroy(() => {
    if (intervalId) clearInterval(intervalId);
  });
</script>

<div class="bg-gradient-to-r from-blue-500/10 to-red-500/10 border border-stroke rounded-2xl p-4 sm:p-5 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
  <div class="space-y-1">
    <div class="flex items-center gap-2">
      <span class="relative flex h-2 w-2">
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
        <span class="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
      </span>
      <h3 class="text-xs font-black uppercase text-content-subtle tracking-wider">Countdown to Election Day</h3>
    </div>
    <p class="text-sm font-semibold text-content">
      {#if status === 'upcoming'}
        The general election will be held on {new Date(electionDate).toLocaleDateString(undefined, { dateStyle: 'long' })}.
      {:else}
        Election status: {status === 'today' ? 'Polls are open today!' : 'Completed'}
      {/if}
    </p>
  </div>

  {#if status === 'upcoming'}
    <div class="flex gap-2 sm:gap-3 justify-center">
      <!-- Days -->
      <div class="flex flex-col items-center bg-surface border border-stroke rounded-xl px-2.5 py-1.5 min-w-[56px] shadow-sm">
        <span class="text-lg font-black text-content tabular-nums leading-none">{days}</span>
        <span class="text-[9px] font-bold text-content-subtle uppercase tracking-wider mt-1">Days</span>
      </div>
      <!-- Hours -->
      <div class="flex flex-col items-center bg-surface border border-stroke rounded-xl px-2.5 py-1.5 min-w-[56px] shadow-sm">
        <span class="text-lg font-black text-content tabular-nums leading-none">{hours}</span>
        <span class="text-[9px] font-bold text-content-subtle uppercase tracking-wider mt-1">Hrs</span>
      </div>
      <!-- Minutes -->
      <div class="flex flex-col items-center bg-surface border border-stroke rounded-xl px-2.5 py-1.5 min-w-[56px] shadow-sm">
        <span class="text-lg font-black text-content tabular-nums leading-none">{minutes}</span>
        <span class="text-[9px] font-bold text-content-subtle uppercase tracking-wider mt-1">Mins</span>
      </div>
      <!-- Seconds -->
      <div class="flex flex-col items-center bg-surface border border-stroke rounded-xl px-2.5 py-1.5 min-w-[56px] shadow-sm">
        <span class="text-lg font-black text-content tabular-nums leading-none">{seconds}</span>
        <span class="text-[9px] font-bold text-content-subtle uppercase tracking-wider mt-1">Secs</span>
      </div>
    </div>
  {:else}
    <div class="px-4 py-2 rounded-xl text-sm font-black border uppercase tracking-wider shadow-sm
      {status === 'today'
        ? 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20 dark:text-emerald-400'
        : 'bg-slate-500/10 text-slate-700 border-slate-500/20 dark:text-slate-400'}"
    >
      {status === 'today' ? 'Polls Open' : 'Voting Closed'}
    </div>
  {/if}
</div>
