<script lang="ts">
  import "../app.css";
  import { navigating, page } from "$app/stores";
  import { onMount } from "svelte";
  import SiteHeader from "$lib/components/SiteHeader.svelte";
  import SiteFooter from "$lib/components/SiteFooter.svelte";

  let isAuthenticated = false;
  let darkMode = false;
  const cloudflareAnalyticsToken = import.meta.env
    .VITE_CLOUDFLARE_WEB_ANALYTICS_TOKEN;

  onMount(() => {
    if (cloudflareAnalyticsToken && !$page.url.pathname.startsWith("/admin")) {
      const script = document.createElement("script");
      script.defer = true;
      script.src = "https://static.cloudflareinsights.com/beacon.min.js";
      script.dataset.cfBeacon = JSON.stringify({
        token: cloudflareAnalyticsToken,
        spa: true,
      });
      document.head.appendChild(script);
    }

    let saved: string | null = null;
    try {
      saved = localStorage.getItem("darkMode");
    } catch (error) {
      console.warn("Failed to read darkMode from localStorage:", error);
    }
    darkMode =
      saved !== null
        ? saved === "true"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", darkMode);

    void (async () => {
      try {
        const { getAuth0Client, isAuthSkipped } = await import("$lib/auth");
        isAuthenticated = isAuthSkipped()
          ? true
          : await (await getAuth0Client()).isAuthenticated();
      } catch {
        isAuthenticated = false;
      }
    })();
  });

  function toggleDark() {
    darkMode = !darkMode;
    document.documentElement.classList.toggle("dark", darkMode);
    try {
      localStorage.setItem("darkMode", String(darkMode));
    } catch (error) {
      console.warn("Failed to write darkMode to localStorage:", error);
    }
  }
</script>

<a
  href="#main-content"
  class="sr-only fixed left-4 top-4 z-[70] rounded-lg bg-blue-700 px-4 py-3 font-bold text-white shadow-lg focus:not-sr-only"
>
  Skip to main content
</a>

<div class="min-h-screen bg-page overflow-x-hidden flex flex-col">
  {#if $navigating}
    <div class="fixed top-0 left-0 right-0 z-[60] h-0.5 overflow-hidden">
      <div
        class="h-full bg-blue-600 animate-[navprogress_1.2s_ease-in-out_infinite]"
      ></div>
    </div>
  {/if}

  <SiteHeader {isAuthenticated} {darkMode} onToggleDark={toggleDark} />

  <main id="main-content" tabindex="-1" class="flex-1">
    <slot />
  </main>

  <SiteFooter />
</div>
