<script lang="ts">
  import "../app.css";
  import { page, navigating } from "$app/stores";
  import { onMount } from "svelte";
  import { writable } from "svelte/store";

  const darkMode = writable(false);
  let isAuthenticated = false;

  onMount(async () => {
    const saved = localStorage.getItem("darkMode");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const enabled = saved !== null ? saved === "true" : prefersDark;
    darkMode.set(enabled);
    document.documentElement.classList.toggle("dark", enabled);

    // Check auth state silently — don't prompt login, just detect if already authenticated
    try {
      const { getAuth0Client, isAuthSkipped } = await import("$lib/auth");
      if (isAuthSkipped()) {
        isAuthenticated = true;
      } else {
        const auth0 = await getAuth0Client();
        isAuthenticated = await auth0.isAuthenticated();
      }
    } catch {
      isAuthenticated = false;
    }
  });

  function toggleDark() {
    darkMode.update(d => {
      const next = !d;
      document.documentElement.classList.toggle("dark", next);
      localStorage.setItem("darkMode", String(next));
      return next;
    });
  }
</script>

<div class="min-h-screen bg-page">
  <!-- Navigation loading bar -->
  {#if $navigating}
    <div class="fixed top-0 left-0 right-0 z-50 h-0.5 overflow-hidden">
      <div class="h-full bg-blue-600 animate-[navprogress_1.2s_ease-in-out_infinite]"></div>
    </div>
  {/if}

  <!-- Navigation -->
  <nav class="bg-surface shadow-sm border-b border-stroke">
    <div class="container mx-auto px-4 py-3 max-w-7xl">
      <div class="flex items-center justify-between">
        <a href="/" class="text-xl sm:text-2xl font-bold text-blue-600 hover:text-blue-700">
          Smarter.vote
        </a>
        <div class="flex items-center gap-4 sm:gap-6 text-sm">
          <a href="/" class="text-content-muted hover:text-content {$page.url.pathname === '/' ? 'font-semibold text-content' : ''}">
            Home
          </a>
          <a href="/about" class="text-content-muted hover:text-content {$page.url.pathname === '/about' ? 'font-semibold text-content' : ''}">
            About
          </a>
          {#if isAuthenticated}
            <a href="/admin" class="text-content-muted hover:text-content {$page.url.pathname.startsWith('/admin') ? 'font-semibold text-content' : ''}">
              Admin
            </a>
          {/if}
          <!-- Dark mode toggle -->
          <button
            on:click={toggleDark}
            class="p-2 rounded-lg text-content-subtle hover:text-content hover:bg-surface-alt transition-colors"
            aria-label="Toggle dark mode"
            title={$darkMode ? "Switch to light mode" : "Switch to dark mode"}
          >
            {#if $darkMode}
              <!-- Sun icon -->
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707M17.657 17.657l-.707-.707M6.343 6.343l-.707-.707M12 8a4 4 0 100 8 4 4 0 000-8z" />
              </svg>
            {:else}
              <!-- Moon icon -->
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            {/if}
          </button>
        </div>
      </div>
    </div>
  </nav>

  <!-- Main Content -->
  <main>
    <slot />
  </main>

  <!-- Footer -->
  <footer class="bg-surface border-t border-stroke mt-12 sm:mt-16">
    <div class="container mx-auto px-4 py-6 sm:py-8 max-w-7xl">
      <div class="text-center text-content-muted text-sm">
        <p class="mb-2">© 2025 Smarter.vote. Analyzing public information to help voters make informed decisions.</p>
        <p class="text-xs text-content-subtle">Always verify information by visiting candidate websites directly. This tool provides analysis for informational purposes only.</p>
        <div class="mt-4">
          <a
            href="https://github.com/sponsors/smartervote"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-pink-300 dark:border-pink-700 text-pink-600 dark:text-pink-400 text-xs font-medium hover:bg-pink-50 dark:hover:bg-pink-950 transition-colors"
          >
            <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 21.593c-.425-.396-8.107-7.112-8.107-12.633C3.893 4.534 7.01 2 10.237 2c1.812 0 3.499.81 4.763 2.12C16.264 2.81 17.951 2 19.763 2 22.99 2 26.107 4.534 26.107 8.96c0 5.521-7.682 12.237-8.107 12.633L12 21.593z"/>
            </svg>
            Sponsor
          </a>
        </div>
      </div>
    </div>
  </footer>
</div>
