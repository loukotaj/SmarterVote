<script lang="ts">
  import { replaceState } from "$app/navigation";
  import { onMount, tick } from "svelte";
  import { getRace } from "$lib/api";
  import CandidateComparison from "$lib/components/compare/CandidateComparison.svelte";
  import type { Candidate, Race, RaceSummary } from "$lib/types";
  import { formatElectionDate } from "$lib/utils/electionDate";

  export let races: RaceSummary[] = [];

  let selectedId = races[0]?.id ?? "";
  let loadedRaces: Record<string, Race> = {};
  let selectedCandidates: Record<string, Candidate[]> = {};
  let loadingId = "";
  let loadError = "";

  function officeLabel(race: RaceSummary): string {
    const office = race.office ?? "Race";
    const normalized = office.toLowerCase();
    if (normalized.includes("house") || normalized.includes("representative")) {
      return "U.S. House";
    }
    if (normalized.includes("senate")) return "U.S. Senate";
    if (normalized.includes("governor") || normalized.includes("gubernatorial"))
      return "Governor";
    return office;
  }

  function activeCandidates(race: Race): Candidate[] {
    return race.candidates.filter((candidate) => !candidate.withdrawn);
  }

  function candidatesFor(
    race: Race,
    selections: Record<string, Candidate[]>,
  ): Candidate[] {
    return selections[race.id] ?? activeCandidates(race).slice(0, 2);
  }

  function toggleCandidate(race: Race, candidateName: string) {
    const current = candidatesFor(race, selectedCandidates);
    const isSelected = current.some(
      (candidate) => candidate.name === candidateName,
    );
    if (isSelected && current.length === 1) return;
    selectedCandidates = {
      ...selectedCandidates,
      [race.id]: isSelected
        ? current.filter((candidate) => candidate.name !== candidateName)
        : [
            ...current,
            ...activeCandidates(race).filter(
              (candidate) =>
                candidate.name === candidateName &&
                !current.some((selected) => selected.name === candidate.name),
            ),
          ],
    };
  }

  async function selectRace(raceId: string, updateUrl = true) {
    selectedId = raceId;
    loadError = "";
    if (updateUrl) {
      const url = new URL(window.location.href);
      url.searchParams.set("race", raceId);
      replaceState(url, {});
    }
    if (loadedRaces[raceId] || loadingId === raceId) return;

    loadingId = raceId;
    try {
      const race = await getRace(raceId);
      loadedRaces = { ...loadedRaces, [raceId]: race };
    } catch (caught) {
      loadError =
        caught instanceof Error
          ? caught.message
          : "We could not load this race guide.";
    } finally {
      if (loadingId === raceId) loadingId = "";
    }
  }

  async function focusRace(index: number) {
    const race = races[index];
    if (!race) return;
    await selectRace(race.id);
    await tick();
    document.getElementById(`ballot-race-tab-${race.id}`)?.focus();
  }

  function handleTabKeydown(event: KeyboardEvent, index: number) {
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % races.length;
    if (event.key === "ArrowLeft")
      nextIndex = (index - 1 + races.length) % races.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = races.length - 1;
    if (nextIndex === null) return;

    event.preventDefault();
    void focusRace(nextIndex);
  }

  onMount(() => {
    const requestedId = new URL(window.location.href).searchParams.get("race");
    const initialId = races.some((race) => race.id === requestedId)
      ? requestedId
      : races[0]?.id;
    if (initialId) void selectRace(initialId, false);
  });

  $: selectedSummary = races.find((race) => race.id === selectedId);
  $: selectedRace = selectedId ? loadedRaces[selectedId] : undefined;
  $: candidates = selectedRace
    ? candidatesFor(selectedRace, selectedCandidates)
    : [];
</script>

{#if races.length}
  <div
    class="mt-7 overflow-hidden rounded-3xl border border-stroke bg-surface shadow-lg"
  >
    <div class="border-b border-stroke bg-surface-alt/50 px-5 py-5 sm:px-7">
      <p
        class="text-xs font-bold uppercase tracking-[0.18em] text-blue-600 dark:text-blue-400"
      >
        Explore your races
      </p>
      <h3 class="mt-1 text-xl font-bold text-content">Your matched races</h3>
      <p class="mt-2 max-w-3xl text-sm leading-6 text-content-muted">
        Choose a race to compare candidates and sourced positions without
        leaving this page.
      </p>
    </div>

    <div
      class="border-b border-stroke bg-surface/95 px-4 py-3 backdrop-blur sm:px-7 lg:sticky lg:top-[65px] lg:z-20"
      role="tablist"
      aria-label="Your matched races"
    >
      <div class="hide-scrollbar flex gap-2 overflow-x-auto pb-1">
        {#each races as race, index}
          <button
            id="ballot-race-tab-{race.id}"
            type="button"
            role="tab"
            aria-selected={selectedId === race.id}
            aria-controls="ballot-race-panel"
            tabindex={selectedId === race.id ? 0 : -1}
            on:click={() => selectRace(race.id)}
            on:keydown={(event) => handleTabKeydown(event, index)}
            class="min-h-11 whitespace-nowrap rounded-full border px-4 py-2 text-sm font-bold transition {selectedId ===
            race.id
              ? 'border-blue-700 bg-blue-700 text-white shadow-md shadow-blue-700/20'
              : 'border-stroke bg-surface text-content-muted hover:border-blue-400 hover:text-blue-700'}"
          >
            {officeLabel(race)}
          </button>
        {/each}
      </div>
    </div>

    <div
      id="ballot-race-panel"
      role="tabpanel"
      aria-labelledby={selectedId ? `ballot-race-tab-${selectedId}` : undefined}
      class="p-4 sm:p-7"
    >
      {#if loadingId === selectedId}
        <div
          class="flex min-h-[16rem] items-center justify-center text-sm font-semibold text-content-muted"
          aria-live="polite"
        >
          Loading this race comparison…
        </div>
      {:else if loadError && !selectedRace}
        <div
          role="alert"
          class="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
        >
          <p class="font-bold">This comparison could not be loaded.</p>
          <p class="mt-1">{loadError}</p>
          <button
            type="button"
            class="mt-3 font-bold text-blue-700 hover:underline dark:text-blue-300"
            on:click={() => selectedId && selectRace(selectedId)}
          >
            Try again
          </button>
        </div>
      {:else if selectedRace && selectedSummary}
        <div
          class="mb-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"
        >
          <div>
            <p
              class="text-xs font-bold uppercase tracking-wider text-content-subtle"
            >
              {officeLabel(selectedSummary)}
            </p>
            <h3
              class="mt-1 text-2xl font-extrabold tracking-tight text-content"
            >
              {selectedRace.title}
            </h3>
            <p class="mt-1 text-sm text-content-muted">
              {formatElectionDate(selectedRace.election_date)}
            </p>
          </div>
          <div class="shrink-0 text-sm font-bold">
            <a
              href="/races/{selectedRace.id}/"
              class="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-blue-700 px-5 py-2.5 text-white shadow-md shadow-blue-900/10 transition hover:-translate-y-0.5 hover:bg-blue-800 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              >View full race guide <span aria-hidden="true">→</span></a
            >
          </div>
        </div>

        {#if candidates.length >= 2}
          <CandidateComparison
            race={selectedRace}
            {candidates}
            compact
            onToggle={(candidateName) =>
              toggleCandidate(selectedRace, candidateName)}
          />
        {:else}
          <div class="rounded-xl bg-surface-alt p-5 text-sm text-content-muted">
            This guide does not yet have enough active candidates for a
            side-by-side comparison.
          </div>
        {/if}
      {/if}
    </div>
  </div>
{/if}
