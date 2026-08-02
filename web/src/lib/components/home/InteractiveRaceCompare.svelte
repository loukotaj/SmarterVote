<script lang="ts">
  import CandidateComparison from "$lib/components/compare/CandidateComparison.svelte";
  import type { Race } from "$lib/types";

  export let races: Race[] = [];
  let selectedId = races[0]?.id ?? "";
  $: if (races.length && !races.some((race) => race.id === selectedId))
    selectedId = races[0].id;
  $: selectedRace = races.find((race) => race.id === selectedId) ?? races[0];
  $: candidates =
    selectedRace?.candidates.filter((candidate) => !candidate.withdrawn) ?? [];

  let scrollContainer: HTMLDivElement | null = null;
  let isMouseDown = false;
  let startX = 0;
  let startScrollLeft = 0;
  let hasDragged = false;

  function moveRace(direction: number) {
    const current = races.findIndex((race) => race.id === selectedId);
    const next = (current + direction + races.length) % races.length;
    selectedId = races[next]?.id ?? selectedId;
    if (scrollContainer && typeof scrollContainer.scrollBy === "function") {
      scrollContainer.scrollBy({ left: direction * 180, behavior: "smooth" });
    }
  }

  function scrollToActivePill() {
    if (!scrollContainer) return;
    const activeBtn = scrollContainer.querySelector<HTMLElement>(
      '[aria-pressed="true"]',
    );
    if (activeBtn && typeof activeBtn.scrollIntoView === "function") {
      activeBtn.scrollIntoView({
        behavior: "smooth",
        inline: "center",
        block: "nearest",
      });
    }
  }

  $: if (selectedId && scrollContainer) {
    setTimeout(scrollToActivePill, 20);
  }

  function handleMouseDown(e: MouseEvent) {
    if (!scrollContainer) return;
    isMouseDown = true;
    hasDragged = false;
    startX = e.pageX - scrollContainer.offsetLeft;
    startScrollLeft = scrollContainer.scrollLeft;
  }

  function handleMouseMove(e: MouseEvent) {
    if (!isMouseDown || !scrollContainer) return;
    const x = e.pageX - scrollContainer.offsetLeft;
    const walk = (x - startX) * 1.5;
    if (Math.abs(walk) > 5) {
      hasDragged = true;
    }
    scrollContainer.scrollLeft = startScrollLeft - walk;
  }

  function handleMouseUp() {
    isMouseDown = false;
  }

  function handlePillClick(e: MouseEvent, raceId: string) {
    if (hasDragged) {
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    selectedId = raceId;
  }

  function handleWheel(e: WheelEvent) {
    if (!scrollContainer) return;
    if (
      e.deltaY !== 0 &&
      scrollContainer.scrollWidth > scrollContainer.clientWidth
    ) {
      e.preventDefault();
      scrollContainer.scrollLeft += e.deltaY * 0.8;
    }
  }
</script>

{#if selectedRace && candidates.length >= 2}
  <div
    class="flex flex-col overflow-hidden rounded-[1.75rem] border border-blue-200 bg-surface shadow-2xl shadow-blue-950/10 lg:h-[min(690px,calc(100vh-10rem))] lg:min-h-[560px] dark:border-blue-900"
  >
    <div
      class="flex flex-col gap-4 border-b border-stroke bg-surface-alt/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-7"
    >
      <div>
        <div
          class="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-blue-600 dark:text-blue-400"
        >
          Featured comparison
        </div>
        <h2
          class="mt-2 text-xl font-extrabold tracking-tight text-content sm:text-2xl"
        >
          {selectedRace.title}
        </h2>
      </div>
      <a
        href="/races/{selectedRace.id}/"
        class="shrink-0 text-sm font-bold text-blue-600 hover:text-blue-800 dark:text-blue-400"
        >Open race page →</a
      >
    </div>

    <div
      class="border-b border-stroke px-4 py-3 sm:px-6"
      aria-label="Choose a featured race"
    >
      <div class="flex items-center gap-3">
        <button
          type="button"
          on:click={() => moveRace(-1)}
          class="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-stroke bg-surface text-lg text-content transition hover:border-blue-400 hover:text-blue-600"
          aria-label="Previous featured race">←</button
        >
        <div
          bind:this={scrollContainer}
          on:mousedown={handleMouseDown}
          on:mousemove={handleMouseMove}
          on:mouseup={handleMouseUp}
          on:mouseleave={handleMouseUp}
          on:wheel={handleWheel}
          role="region"
          aria-label="Featured races scroll list"
          class="hide-scrollbar flex min-w-0 flex-1 cursor-grab select-none gap-2 overflow-x-auto py-1 active:cursor-grabbing"
        >
          {#each races as race, index}
            <button
              type="button"
              on:click={(e) => handlePillClick(e, race.id)}
              aria-pressed={selectedId === race.id}
              class="min-h-11 whitespace-nowrap rounded-full border px-4 py-2 text-sm font-bold transition {selectedId ===
              race.id
                ? 'border-blue-600 bg-blue-600 text-white shadow-md shadow-blue-600/20'
                : 'border-stroke bg-surface text-content-muted hover:border-blue-400 hover:text-blue-700'}"
            >
              <span class="mr-1 opacity-70"
                >{String(index + 1).padStart(2, "0")}</span
              >
              {race.jurisdiction} · {race.office}
            </button>
          {/each}
        </div>
        <button
          type="button"
          on:click={() => moveRace(1)}
          class="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-stroke bg-surface text-lg text-content transition hover:border-blue-400 hover:text-blue-600"
          aria-label="Next featured race">→</button
        >
      </div>
    </div>

    <div
      class="min-h-0 flex-1 overflow-y-auto p-3 lg:p-5"
      aria-label="Scrollable featured comparison"
    >
      <CandidateComparison
        race={selectedRace}
        {candidates}
        compact
        showQuality
      />
      <div
        class="pointer-events-none sticky bottom-0 mt-[-2.75rem] hidden justify-center bg-gradient-to-t from-surface via-surface/95 to-transparent pb-2 pt-10 lg:flex"
      >
        <span
          class="rounded-full border border-stroke bg-surface px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-content-subtle shadow-sm"
          >Scroll for more issues ↓</span
        >
      </div>
    </div>
  </div>
{/if}
