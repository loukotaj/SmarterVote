<script lang="ts">
  import { browser } from "$app/environment";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import { onMount, tick } from "svelte";
  import type { RaceSummary } from "$lib/types";
  import { getRaceSummaries } from "$lib/api";
  import { candidateSlug } from "$lib/utils/format";
  import { debounce } from "$lib/utils/debounce";
  import { matchesSearchQuery } from "$lib/utils/search";

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
  let searchRaces: RaceSummary[] = races;
  let searchLoading = false;
  let searchLoaded = races.length > 0;
  let searchLoadError = false;
  let searchLoadPromise: Promise<void> | null = null;
  let mobileNavOpen = false;
  let mobileSearchOpen = false;
  let siteHeader: HTMLElement;
  const resultsId = "site-search-results";

  onMount(() => {
    const updateHeaderHeight = () => {
      document.documentElement.style.setProperty(
        "--site-header-height",
        `${siteHeader.offsetHeight}px`,
      );
    };

    updateHeaderHeight();
    const resizeObserver = new ResizeObserver(updateHeaderHeight);
    resizeObserver.observe(siteHeader);

    return () => resizeObserver.disconnect();
  });

  async function ensureSearchRaces() {
    if (!browser || searchLoaded || searchLoadPromise) return searchLoadPromise;
    searchLoading = true;
    searchLoadError = false;
    searchLoadPromise = getRaceSummaries()
      .then((loadedRaces) => {
        searchRaces = loadedRaces;
        searchLoaded = true;
      })
      .catch(() => {
        searchLoadError = true;
      })
      .finally(() => {
        searchLoading = false;
        searchLoadPromise = null;
      });
    return searchLoadPromise;
  }

  $: raceMatches = query.trim()
    ? searchRaces
        .filter((race) => {
          return matchesSearchQuery(
            query,
            race.title,
            race.office,
            race.state,
            race.jurisdiction,
          );
        })
        .slice(0, 5)
    : [];
  $: candidateMatches = query.trim()
    ? searchRaces
        .flatMap((race) =>
          race.candidates
            .filter((candidate) => {
              return matchesSearchQuery(
                query,
                candidate.name,
                candidate.party,
                race.title,
                race.office,
                race.state,
                race.jurisdiction,
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
      if (urlQuery) void ensureSearchRaces();
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
    if (open) void ensureSearchRaces();
    if ($page.url.pathname === "/") {
      lastQuery = query.trim();
      updateHomepageQuery(lastQuery);
    }
  }

  function selectRace(id: string) {
    open = false;
    mobileSearchOpen = false;
    query = "";
    goto(`/races/${id}`);
  }

  function selectCandidate(raceId: string, name: string) {
    open = false;
    mobileSearchOpen = false;
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
    if (event.key === "Escape") {
      mobileNavOpen = false;
      mobileSearchOpen = false;
    }
    if (
      event.key === "/" &&
      !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName || "")
    ) {
      event.preventDefault();
      mobileSearchOpen = true;
      void tick().then(() => {
        searchInput?.focus();
        searchInput?.select();
      });
    }
  }

  async function toggleMobileSearch() {
    mobileSearchOpen = !mobileSearchOpen;
    mobileNavOpen = false;
    if (mobileSearchOpen) {
      await tick();
      searchInput?.focus();
    } else {
      open = false;
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
  bind:this={siteHeader}
  class="sticky top-0 z-50 bg-surface/90 backdrop-blur-md shadow-sm border-b border-stroke/50"
>
  <div class="container mx-auto max-w-7xl px-4 py-3">
    <div class="flex flex-wrap items-center gap-1 sm:gap-3 lg:flex-nowrap">
      <a
        href="/"
        class="mr-auto text-xl sm:text-2xl font-bold text-primary hover:text-primary/80 whitespace-nowrap"
        aria-label="Smarter.Vote home"
      >
        Smarter.Vote
      </a>

      <button
        type="button"
        class="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg text-content-muted hover:bg-surface-alt hover:text-content sm:hidden"
        aria-label={mobileSearchOpen ? "Close search" : "Open search"}
        aria-controls="site-search"
        aria-expanded={mobileSearchOpen}
        on:click={toggleMobileSearch}
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          class="h-5 w-5"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          {#if mobileSearchOpen}
            <path stroke-linecap="round" d="M6 6l12 12M18 6L6 18" />
          {:else}
            <circle cx="11" cy="11" r="7" />
            <path stroke-linecap="round" d="m16 16 4 4" />
          {/if}
        </svg>
      </button>

      <button
        type="button"
        class="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg text-content-muted hover:bg-surface-alt hover:text-content sm:hidden"
        aria-label={mobileNavOpen
          ? "Close navigation menu"
          : "Open navigation menu"}
        aria-controls="primary-navigation"
        aria-expanded={mobileNavOpen}
        on:click={() => {
          mobileNavOpen = !mobileNavOpen;
          mobileSearchOpen = false;
          open = false;
        }}
      >
        <span aria-hidden="true">{mobileNavOpen ? "×" : "☰"}</span>
      </button>

      <nav
        id="primary-navigation"
        class="order-3 w-full flex-wrap items-center gap-x-4 gap-y-1 text-sm {mobileNavOpen
          ? 'flex'
          : 'hidden'} sm:flex sm:justify-start lg:order-none lg:w-auto lg:flex-nowrap"
        aria-label="Primary navigation"
      >
        {#each primaryLinks as link}
          <a
            href={link.href}
            on:click={() => (mobileNavOpen = false)}
            class:font-semibold={$page.url.pathname.startsWith(link.href)}
            class="inline-flex min-h-11 items-center whitespace-nowrap px-1 text-content-muted hover:text-content"
          >
            {link.label}
          </a>
        {/each}
        {#if isAuthenticated}
          <a
            href="/admin/"
            on:click={() => (mobileNavOpen = false)}
            class="inline-flex min-h-11 items-center whitespace-nowrap px-1 text-content-muted hover:text-content"
            >Admin</a
          >
        {/if}
      </nav>

      <div
        class="relative order-2 w-full {mobileSearchOpen
          ? 'block'
          : 'hidden'} sm:order-none sm:block sm:w-64 lg:w-72"
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
          on:focus={() => {
            open = Boolean(query.trim());
            if (open) void ensureSearchRaces();
          }}
          on:keydown={handleKeydown}
          class="min-h-11 w-full rounded-full border border-stroke bg-surface-alt py-2 pl-4 pr-12 text-sm text-content focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary"
          placeholder="Search elections or candidates"
          autocomplete="off"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open && totalMatches > 0}
          aria-controls={resultsId}
          aria-activedescendant={activeIndex >= 0
            ? `site-search-option-${activeIndex}`
            : undefined}
        />
        {#if query}
          <button
            type="button"
            on:click={clearSearch}
            class="absolute inset-y-0 right-0 min-h-11 min-w-11 px-3 text-content-subtle hover:text-content"
            aria-label="Clear search">×</button
          >
        {/if}

        {#if open && totalMatches > 0}
          <div
            id={resultsId}
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
                  id={`site-search-option-${index}`}
                  type="button"
                  on:click={() => selectRace(race.id)}
                  class:bg-surface-alt={index === activeIndex}
                  class="block min-h-11 w-full px-3 py-2 text-left text-xs text-content hover:bg-surface-alt"
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
                  id={`site-search-option-${itemIndex}`}
                  type="button"
                  on:click={() =>
                    selectCandidate(candidate.raceId, candidate.name)}
                  class:bg-surface-alt={itemIndex === activeIndex}
                  class="block min-h-11 w-full px-3 py-2 text-left text-xs text-content hover:bg-surface-alt"
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
        {:else if open && searchLoading}
          <div
            class="absolute left-0 right-0 top-full mt-2 rounded-xl border border-stroke bg-surface px-4 py-3 text-xs text-content-subtle shadow-xl"
            role="status"
          >
            Loading search results&hellip;
          </div>
        {:else if open && searchLoaded && query.trim()}
          <div
            class="absolute left-0 right-0 top-full mt-2 rounded-xl border border-stroke bg-surface px-4 py-3 text-xs text-content-subtle shadow-xl"
            role="status"
          >
            No matching elections or candidates.
          </div>
        {:else if open && searchLoadError}
          <div
            class="absolute left-0 right-0 top-full mt-2 rounded-xl border border-stroke bg-surface px-4 py-3 text-xs text-red-700 shadow-xl dark:text-red-300"
            role="alert"
          >
            Search is temporarily unavailable. Press Enter to browse elections.
          </div>
        {/if}
      </div>

      <button
        type="button"
        on:click={onToggleDark}
        class="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg p-2 text-content-subtle hover:bg-surface-alt hover:text-content"
        aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
      >
        {darkMode ? "☀" : "☾"}
      </button>
    </div>
  </div>
</header>
