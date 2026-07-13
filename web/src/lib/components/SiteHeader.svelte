<script lang="ts">
  import { browser } from "$app/environment";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import type { RaceSummary } from "$lib/types";
  import { candidateSlug } from "$lib/utils/format";
  import { debounce } from "$lib/utils/debounce";

  export let races: RaceSummary[] = [];
  export let isAuthenticated = false;
  export let darkMode = false;
  export let onToggleDark: () => void;

  let query = "";
  let lastQuery = "";
  let open = false;
  let activeIndex = -1;
  let searchContainer: HTMLElement;
  let searchInput: HTMLInputElement;

  $: raceMatches = query.trim()
    ? races
        .filter((race) => {
          const q = query.trim().toLowerCase();
          return [race.title, race.office, race.state, race.jurisdiction].some(
            (value) => value?.toLowerCase().includes(q),
          );
        })
        .slice(0, 5)
    : [];
  $: candidateMatches = query.trim()
    ? races
        .flatMap((race) =>
          race.candidates
            .filter((candidate) => {
              const q = query.trim().toLowerCase();
              return (
                candidate.name.toLowerCase().includes(q) ||
                candidate.party?.toLowerCase().includes(q)
              );
            })
            .map((candidate) => ({
              ...candidate,
              raceId: race.id,
              raceTitle: race.title || race.id,
            })),
        )
        .slice(0, 5)
    : [];
  $: totalMatches = raceMatches.length + candidateMatches.length;

  $: if (browser && $page.url.pathname === "/") {
    const urlQuery = $page.url.searchParams.get("q") || "";
    if (urlQuery !== lastQuery) {
      lastQuery = urlQuery;
      query = urlQuery;
    }
  } else {
    lastQuery = "";
  }

  const updateHomepageQuery = debounce((value: string) => {
    if ($page.url.pathname !== "/") return;
    const params = new URLSearchParams($page.url.searchParams);
    value ? params.set("q", value) : params.delete("q");
    goto(`/?${params}`, {
      replaceState: true,
      keepFocus: true,
      noScroll: true,
    });
  }, 150);

  function handleInput() {
    activeIndex = -1;
    open = Boolean(query.trim());
    if ($page.url.pathname === "/") {
      lastQuery = query.trim();
      updateHomepageQuery(lastQuery);
    }
  }

  function selectRace(id: string) {
    open = false;
    query = "";
    goto(`/races/${id}`);
  }

  function selectCandidate(raceId: string, name: string) {
    open = false;
    query = "";
    goto(`/races/${raceId}/${candidateSlug(name)}`);
  }

  function clearSearch() {
    query = "";
    lastQuery = "";
    open = false;
    updateHomepageQuery("");
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "ArrowDown" && totalMatches) {
      event.preventDefault();
      activeIndex = (activeIndex + 1) % totalMatches;
    } else if (event.key === "ArrowUp" && totalMatches) {
      event.preventDefault();
      activeIndex = (activeIndex - 1 + totalMatches) % totalMatches;
    } else if (event.key === "Escape") {
      open = false;
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (activeIndex >= 0 && activeIndex < raceMatches.length)
        selectRace(raceMatches[activeIndex].id);
      else if (
        activeIndex >= raceMatches.length &&
        activeIndex < totalMatches
      ) {
        const candidate = candidateMatches[activeIndex - raceMatches.length];
        selectCandidate(candidate.raceId, candidate.name);
      } else if (query.trim())
        goto(`/elections/?q=${encodeURIComponent(query.trim())}`);
    }
  }

  function handleWindowKeydown(event: KeyboardEvent) {
    if (
      event.key === "/" &&
      !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName || "")
    ) {
      event.preventDefault();
      searchInput?.focus();
      searchInput?.select();
    }
  }

  function handleWindowClick(event: MouseEvent) {
    if (searchContainer && !searchContainer.contains(event.target as Node))
      open = false;
  }

  const primaryLinks = [
    { href: "/my-ballot/", label: "My Ballot" },
    { href: "/elections/", label: "Elections" },
    { href: "/forecast/", label: "Forecast" },
    { href: "/about/", label: "About" },
    { href: "/support/", label: "Support" },
  ];
</script>

<svelte:window on:click={handleWindowClick} on:keydown={handleWindowKeydown} />

<header
  class="sticky top-0 z-50 bg-surface/90 backdrop-blur-md shadow-sm border-b border-stroke/50"
>
  <div class="container mx-auto max-w-7xl px-4 py-3">
    <div class="flex flex-wrap items-center gap-3 lg:flex-nowrap">
      <a
        href="/"
        class="mr-auto text-xl sm:text-2xl font-bold text-blue-600 hover:text-blue-700 whitespace-nowrap"
        aria-label="Smarter.Vote home"
      >
        Smarter.Vote
      </a>

      <nav
        class="order-3 flex w-full items-center gap-x-4 gap-y-2 overflow-x-auto text-sm lg:order-none lg:w-auto"
        aria-label="Primary navigation"
      >
        {#each primaryLinks as link}
          <a
            href={link.href}
            class:font-semibold={$page.url.pathname.startsWith(link.href)}
            class="whitespace-nowrap text-content-muted hover:text-content"
          >
            {link.label}
          </a>
        {/each}
        {#if isAuthenticated}
          <a
            href="/admin/"
            class="whitespace-nowrap text-content-muted hover:text-content"
            >Admin</a
          >
        {/if}
      </nav>

      <div
        class="relative order-2 w-full sm:order-none sm:w-64 lg:w-72"
        bind:this={searchContainer}
      >
        <label class="sr-only" for="site-search"
          >Search elections and candidates</label
        >
        <input
          id="site-search"
          bind:this={searchInput}
          bind:value={query}
          on:input={handleInput}
          on:focus={() => (open = Boolean(query.trim()))}
          on:keydown={handleKeydown}
          class="w-full rounded-full border border-stroke bg-surface-alt py-2 pl-4 pr-9 text-sm text-content focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Search elections or candidates"
          autocomplete="off"
        />
        {#if query}
          <button
            type="button"
            on:click={clearSearch}
            class="absolute inset-y-0 right-0 px-3 text-content-subtle hover:text-content"
            aria-label="Clear search">×</button
          >
        {/if}

        {#if open && totalMatches > 0}
          <div
            class="absolute left-0 right-0 top-full mt-2 max-h-96 overflow-y-auto rounded-xl border border-stroke bg-surface py-2 shadow-xl"
            role="listbox"
          >
            {#if raceMatches.length}
              <p
                class="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-content-subtle"
              >
                Elections
              </p>
              {#each raceMatches as race, index}
                <button
                  type="button"
                  on:click={() => selectRace(race.id)}
                  class:bg-surface-alt={index === activeIndex}
                  class="block w-full px-3 py-2 text-left text-xs text-content hover:bg-surface-alt"
                  role="option"
                  aria-selected={index === activeIndex}
                >
                  <span class="block truncate font-medium"
                    >{race.title || race.id}</span
                  >
                  <span class="block truncate text-content-subtle"
                    >{race.office || ""}{race.state
                      ? ` · ${race.state}`
                      : ""}</span
                  >
                </button>
              {/each}
            {/if}
            {#if candidateMatches.length}
              <p
                class="border-t border-stroke px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-content-subtle"
              >
                Candidates
              </p>
              {#each candidateMatches as candidate, index}
                {@const itemIndex = raceMatches.length + index}
                <button
                  type="button"
                  on:click={() =>
                    selectCandidate(candidate.raceId, candidate.name)}
                  class:bg-surface-alt={itemIndex === activeIndex}
                  class="block w-full px-3 py-2 text-left text-xs text-content hover:bg-surface-alt"
                  role="option"
                  aria-selected={itemIndex === activeIndex}
                >
                  <span class="block truncate font-medium"
                    >{candidate.name}</span
                  >
                  <span class="block truncate text-content-subtle"
                    >{candidate.party || ""} · {candidate.raceTitle}</span
                  >
                </button>
              {/each}
            {/if}
          </div>
        {/if}
      </div>

      <button
        type="button"
        on:click={onToggleDark}
        class="rounded-lg p-2 text-content-subtle hover:bg-surface-alt hover:text-content"
        aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
      >
        {darkMode ? "☀" : "☾"}
      </button>
    </div>
  </div>
</header>
