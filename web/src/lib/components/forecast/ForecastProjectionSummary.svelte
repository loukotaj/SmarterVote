<script lang="ts">
  import { formatNet } from "$lib/utils/forecast";
  import {
    oneDecimal,
    partyClass,
    probability,
  } from "$lib/utils/forecastPresentation";

  export let label: string;
  export let controlParty: "Democratic" | "Republican" | "Other";
  export let threshold: number;
  export let projectedSeats: Record<string, number>;
  export let totalExpected: number;
  export let outcomeProbabilities: Record<string, number> | undefined;
  export let expectedSeats: Record<string, number> | undefined;
  export let netChange: Record<string, number>;

  const controlParties: ("Democratic" | "Republican" | "Other")[] = [
    "Democratic",
    "Republican",
    "Other",
  ];
</script>

<!-- Projection Summary Stat Card -->
<div
  class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md"
>
  <p class="text-xs font-bold uppercase text-content-subtle tracking-wider">
    {label} Projected Seats
  </p>

  <h3
    class="mt-3 text-3xl font-extrabold text-content flex items-baseline gap-2"
  >
    <span class={partyClass(controlParty)}>
      {controlParty === "Other"
        ? "No Clear Control"
        : `${controlParty} Control`}
    </span>
  </h3>

  <p class="mt-1 text-xs text-content-subtle font-medium">
    {threshold} seats needed for majority
  </p>

  <!-- Seat Distribution Bar Chart -->
  <div class="mt-6 space-y-1.5">
    <div
      class="flex items-center justify-between text-xs font-bold text-content-muted"
    >
      <span>Democrat: {projectedSeats.Democratic ?? 0}</span>
      <span>Republican: {projectedSeats.Republican ?? 0}</span>
    </div>

    <div
      class="h-6 rounded-full overflow-hidden bg-surface-alt flex border border-stroke/60"
    >
      <div
        class="bg-blue-600 dark:bg-blue-500 transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner"
        style={`width: ${Math.min(
          100,
          ((projectedSeats.Democratic ?? 0) / totalExpected) * 100,
        )}%`}
        title="Democratic projected seats"
      >
        {#if (projectedSeats.Democratic ?? 0) > 20}
          {projectedSeats.Democratic}
        {/if}
      </div>
      {#if projectedSeats.Other}
        <div
          class="bg-slate-400 dark:bg-slate-500 transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner"
          style={`width: ${Math.min(
            100,
            ((projectedSeats.Other ?? 0) / totalExpected) * 100,
          )}%`}
          title="Other projected seats"
        >
          {#if (projectedSeats.Other ?? 0) > totalExpected * 0.05}
            {projectedSeats.Other}
          {/if}
        </div>
      {/if}
      <div
        class="bg-red-600 dark:bg-red-500 transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner ml-auto"
        style={`width: ${Math.min(
          100,
          ((projectedSeats.Republican ?? 0) / totalExpected) * 100,
        )}%`}
        title="Republican projected seats"
      >
        {#if (projectedSeats.Republican ?? 0) > 20}
          {projectedSeats.Republican}
        {/if}
      </div>
    </div>

    <div class="flex justify-between text-[10px] text-content-subtle px-1">
      <span>Total: {totalExpected}</span>
      <span>Majority Line: {threshold}</span>
    </div>
    {#if outcomeProbabilities}
      <div class="mt-4 grid grid-cols-2 gap-2 text-xs">
        <div
          class="rounded-lg border border-blue-500/20 bg-blue-500/10 px-3 py-2"
        >
          <div class="font-bold text-blue-700 dark:text-blue-300">
            {probability(outcomeProbabilities.Democratic)}
          </div>
          <div
            class="text-[10px] text-content-subtle font-semibold uppercase tracking-wider"
          >
            Dem control
          </div>
        </div>
        <div
          class="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-right"
        >
          <div class="font-bold text-red-700 dark:text-red-300">
            {probability(outcomeProbabilities.Republican)}
          </div>
          <div
            class="text-[10px] text-content-subtle font-semibold uppercase tracking-wider"
          >
            GOP control
          </div>
        </div>
      </div>
    {/if}
    {#if expectedSeats}
      <p class="mt-3 text-[10px] text-content-subtle">
        Expected seats: D {oneDecimal(expectedSeats.Democratic)}, R {oneDecimal(
          expectedSeats.Republican,
        )}
        {#if expectedSeats.Other}
          , Other {oneDecimal(expectedSeats.Other)}
        {/if}
      </p>
    {/if}
  </div>

  <!-- Net Seats Change Grid -->
  <div class="mt-6 pt-5 border-t border-stroke/40 grid grid-cols-3 gap-3">
    {#each controlParties as party}
      <div
        class="bg-surface-alt/40 border border-stroke/40 rounded-xl px-2.5 py-2 text-center shadow-inner"
      >
        <div
          class="text-[10px] text-content-subtle font-bold uppercase tracking-wider"
        >
          {party.slice(0, 3)}
        </div>
        <div class={`text-xl font-black mt-1 ${partyClass(party)}`}>
          {projectedSeats[party] ?? 0}
        </div>
        <div
          class="text-[10px] text-content-subtle font-semibold tabular-nums mt-0.5"
        >
          {formatNet(netChange[party] ?? 0)} net
        </div>
      </div>
    {/each}
  </div>
</div>
