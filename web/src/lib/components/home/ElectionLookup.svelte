<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte";
  import BallotExplorer from "$lib/components/ballot/BallotExplorer.svelte";
  import type { RaceSummary } from "$lib/types";
  import {
    lookupElectionGeography,
    matchingNationalRaces,
  } from "$lib/services/electionLookup";

  export let races: RaceSummary[] = [];
  const dispatch = createEventDispatcher<{ exploring: boolean }>();

  let address = "";
  let loading = false;
  let submitted = false;
  let state = "";
  let district = "";
  let results: RaceSummary[] = [];
  let error = "";

  const SESSION_KEY = "smarterVote.ballot";

  onMount(() => {
    try {
      const saved = JSON.parse(
        sessionStorage.getItem(SESSION_KEY) ?? "null"
      ) as {
        state?: string;
        district?: string;
        raceIds?: string[];
      } | null;
      if (!saved?.state || !saved.district || !Array.isArray(saved.raceIds))
        return;
      const restored = saved.raceIds
        .map((id) => races.find((race) => race.id === id))
        .filter((race): race is RaceSummary => Boolean(race));
      if (!restored.length) return;
      state = saved.state;
      district = saved.district;
      results = restored;
      submitted = true;
      dispatch("exploring", true);
    } catch {
      sessionStorage.removeItem(SESSION_KEY);
    }
  });

  async function findElections() {
    const query = address.trim();
    if (!query || loading) return;
    loading = true;
    submitted = false;
    error = "";
    results = [];
    try {
      const geography = await lookupElectionGeography(query);
      state = geography.state;
      district = geography.congressionalDistrict;
      results = matchingNationalRaces(races, geography);
      submitted = true;
      dispatch("exploring", true);
      sessionStorage.setItem(
        SESSION_KEY,
        JSON.stringify({
          state,
          district,
          raceIds: results.map((race) => race.id),
        })
      );
      address = "";
    } catch (caught) {
      error =
        caught instanceof Error
          ? caught.message
          : "We could not look up that address.";
    } finally {
      loading = false;
    }
  }

  function searchAnotherAddress() {
    submitted = false;
    results = [];
    state = "";
    district = "";
    error = "";
    sessionStorage.removeItem(SESSION_KEY);
    const url = new URL(window.location.href);
    url.searchParams.delete("race");
    window.history.replaceState({}, "", url);
    dispatch("exploring", false);
  }
</script>

<div class="min-w-0">
  {#if !submitted}
    <div
      class="relative overflow-hidden rounded-[2rem] border border-blue-100 bg-surface/95 p-6 shadow-2xl shadow-blue-950/10 backdrop-blur sm:p-10 dark:border-blue-900"
    >
      <div
        class="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-blue-700 via-blue-500 to-sky-400"
        aria-hidden="true"
      />
      <div class="flex items-center justify-between gap-4">
        <div>
          <p
            class="text-xs font-bold uppercase tracking-[0.18em] text-blue-600 dark:text-blue-400"
          >
            Address search
          </p>
          <h2 class="mt-2 text-3xl font-bold tracking-tight text-content">
            Where are you registered to vote?
          </h2>
        </div>
        <span
          class="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
          >Free</span
        >
      </div>
      <p class="mt-4 max-w-xl leading-7 text-content-muted">
        Enter the full residential address where you are registered. We’ll
        identify your district and show the U.S. House, Senate, and governor
        research available for it.
      </p>

      <form class="mt-7" on:submit|preventDefault={findElections}>
        <label for="home-address" class="text-sm font-semibold text-content"
          >Home address</label
        >
        <input
          id="home-address"
          bind:value={address}
          required
          autocomplete="street-address"
          placeholder="1600 Pennsylvania Ave NW, Washington, DC 20500"
          class="mt-2 min-h-[60px] w-full rounded-xl border border-stroke bg-surface px-5 text-base text-content shadow-sm transition placeholder:text-content-subtle hover:border-blue-300 focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-500/15"
        />
        <button
          type="submit"
          disabled={loading || !address.trim()}
          class="mt-4 inline-flex min-h-[56px] w-full items-center justify-center rounded-xl bg-blue-700 px-6 font-bold text-white shadow-lg shadow-blue-900/10 transition hover:-translate-y-0.5 hover:bg-blue-800 hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0"
          >{loading ? "Finding your districts…" : "Show my elections"}</button
        >
      </form>

      <p class="mt-4 flex gap-2 text-xs leading-5 text-content-subtle">
        <span aria-hidden="true">⌁</span>
        <span
          >Your address is sent directly to the U.S. Census Geocoder and is not
          saved by Smarter.Vote.</span
        >
      </p>
      <div class="mt-4 border-t border-stroke pt-4 text-sm text-content-muted">
        <strong class="text-content">Coverage today:</strong> U.S. House,
        Senate, and governor research. This is not yet a complete local ballot.
        <a
          href="/elections/"
          class="ml-1 font-semibold text-blue-600 hover:underline dark:text-blue-400"
          >Browse national elections</a
        >
      </div>

      {#if error}
        <div
          role="alert"
          class="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
        >
          <p class="font-semibold">We couldn’t complete the lookup.</p>
          <p class="mt-1">
            {error} Check the full street, city, state, and ZIP, or browse by state.
          </p>
        </div>
      {/if}
    </div>
  {/if}

  {#if submitted}
    <section
      class="rounded-[2rem] border border-stroke bg-surface p-4 shadow-xl shadow-blue-950/5 sm:p-7 lg:p-9"
      aria-live="polite"
    >
      <div
        class="flex flex-col gap-5 border-b border-stroke pb-6 sm:flex-row sm:items-end sm:justify-between"
      >
        <div>
          <p
            class="text-xs font-bold uppercase tracking-[0.18em] text-blue-600 dark:text-blue-400"
          >
            {state} · U.S. House District {Number(district)}
          </p>
          <h1
            class="mt-2 text-3xl font-extrabold tracking-tight text-content sm:text-4xl"
          >
            Your election guide
          </h1>
          <p
            class="mt-2 max-w-3xl text-sm leading-6 text-content-muted sm:text-base"
          >
            Explore every published race we matched to your district. This is
            not a complete official ballot; confirm voting information with your
            election authority.
          </p>
        </div>
        <button
          type="button"
          on:click={searchAnotherAddress}
          class="inline-flex min-h-[44px] shrink-0 items-center justify-center rounded-xl border border-stroke bg-surface px-4 text-sm font-bold text-content transition hover:border-blue-400 hover:bg-surface-alt focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          ← Search another address
        </button>
      </div>
      {#if results.length}
        <BallotExplorer races={results} />
      {:else}
        <div
          class="mt-5 rounded-xl bg-surface-alt p-4 text-sm text-content-muted"
        >
          We identified your district, but no matching published national guide
          is available yet. This does not mean you have no elections.
        </div>
      {/if}
    </section>
  {/if}
</div>
