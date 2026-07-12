<script lang="ts">
  import type { RaceSummary } from "$lib/types";
  import {
    lookupElectionGeography,
    matchingNationalRaces,
  } from "$lib/services/electionLookup";

  export let races: RaceSummary[] = [];

  let address = "";
  let loading = false;
  let submitted = false;
  let state = "";
  let district = "";
  let results: RaceSummary[] = [];
  let error = "";

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
</script>

<div
  class="rounded-3xl border border-blue-100 bg-surface/95 p-5 shadow-xl shadow-blue-950/10 sm:p-7 dark:border-blue-900"
>
  <div class="flex items-center justify-between gap-4">
    <div>
      <p
        class="text-xs font-bold uppercase tracking-[0.18em] text-blue-600 dark:text-blue-400"
      >
        Address lookup
      </p>
      <h2 class="mt-2 text-2xl font-bold text-content">Find my elections</h2>
    </div>
    <span
      class="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
      >Free</span
    >
  </div>
  <p class="mt-3 leading-6 text-content-muted">
    Enter your home address to identify the U.S. House and Senate research that
    applies to you.
  </p>

  <form class="mt-5" on:submit|preventDefault={findElections}>
    <label for="home-address" class="text-sm font-semibold text-content"
      >Home address</label
    >
    <input
      id="home-address"
      bind:value={address}
      required
      autocomplete="street-address"
      placeholder="1600 Pennsylvania Ave NW, Washington, DC 20500"
      class="mt-2 min-h-[54px] w-full rounded-xl border border-stroke bg-surface px-4 text-content shadow-sm placeholder:text-content-subtle focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
    />
    <button
      type="submit"
      disabled={loading || !address.trim()}
      class="mt-3 inline-flex min-h-[52px] w-full items-center justify-center rounded-xl bg-blue-600 px-6 font-bold text-white shadow-sm transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
      >{loading ? "Finding your districts…" : "Find my elections"}</button
    >
  </form>

  <p class="mt-3 text-xs leading-5 text-content-subtle">
    Your address is sent directly to the U.S. Census Geocoder and is not saved
    by Smarter.Vote.
  </p>
  <div class="mt-4 border-t border-stroke pt-4 text-sm text-content-muted">
    <strong class="text-content">Coverage today:</strong> U.S. House and Senate
    research. This is not a complete ballot.
    <a
      href="/elections/"
      class="ml-1 font-semibold text-blue-600 hover:underline dark:text-blue-400"
      >Browse all national elections</a
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

{#if submitted}
  <section
    class="mt-6 rounded-3xl border border-stroke bg-surface p-5 shadow-lg sm:p-7"
    aria-live="polite"
  >
    <p
      class="text-xs font-bold uppercase tracking-[0.18em] text-blue-600 dark:text-blue-400"
    >
      {state} · U.S. House District {Number(district)}
    </p>
    <h2 class="mt-2 text-2xl font-bold text-content">
      National elections near you
    </h2>
    <p class="mt-2 text-sm leading-6 text-content-muted">
      These are the published national races Smarter.Vote can match. Confirm
      your complete ballot with your state or local election authority.
    </p>
    {#if results.length}
      <div class="mt-5 space-y-3">
        {#each results as race (race.id)}
          <a
            href={`/races/${race.id}`}
            class="group flex items-center justify-between gap-4 rounded-xl border border-stroke bg-surface p-4 transition hover:border-blue-300 hover:shadow-sm"
          >
            <span>
              <span
                class="block font-semibold text-content group-hover:text-blue-700 dark:group-hover:text-blue-300"
                >{race.title ?? race.office ?? "Election guide"}</span
              >
              <span class="mt-1 block text-xs text-content-subtle"
                >{race.candidates.length} candidate{race.candidates.length === 1
                  ? ""
                  : "s"} · Election day {new Date(
                  `${race.election_date}T12:00:00`
                ).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}</span
              >
            </span>
            <span aria-hidden="true" class="text-lg text-blue-600">→</span>
          </a>
        {/each}
      </div>
    {:else}
      <div
        class="mt-5 rounded-xl bg-surface-alt p-4 text-sm text-content-muted"
      >
        We identified your district, but no matching published national guide is
        available yet. This does not mean you have no elections.
      </div>
    {/if}
  </section>
{/if}
