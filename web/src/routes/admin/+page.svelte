<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { getAuth0Client } from "$lib/auth";

  let authError = "";

  function clearAuthQueryParams() {
    const url = new URL(window.location.href);
    ["code", "state", "error", "error_description"].forEach((p) =>
      url.searchParams.delete(p)
    );
    history.replaceState({}, "", `${url.pathname}${url.search}`);
  }

  async function startLogin() {
    const auth0 = await getAuth0Client();
    await auth0.loginWithRedirect({
      authorizationParams: { prompt: "login" },
    });
  }

  onMount(async () => {
    try {
      const auth0 = await getAuth0Client();
      const params = new URLSearchParams(window.location.search);

      if (params.has("error")) {
        const description =
          params.get("error_description") || "Access denied by Auth0.";
        clearAuthQueryParams();
        authError = decodeURIComponent(description.replace(/\+/g, " "));
        return;
      }

      if (params.has("code")) {
        try {
          await auth0.handleRedirectCallback();
          clearAuthQueryParams();
          await goto("/admin/pipeline", { replaceState: true });
          return;
        } catch {
          clearAuthQueryParams();
          authError =
            "Authentication callback failed. Please try signing in again.";
          return;
        }
      }

      const isAuthenticated = await auth0.isAuthenticated().catch(() => false);
      if (isAuthenticated) {
        await goto("/admin/pipeline", { replaceState: true });
        return;
      }

      await startLogin();
    } catch {
      authError =
        "Unable to start login. Please verify Auth0 domain, client id, and audience configuration.";
    }
  });
</script>

{#if authError}
  <div class="max-w-xl mx-auto mt-16 px-4">
    <div
      class="rounded-lg border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm"
    >
      <p>{authError}</p>
      <button
        class="mt-3 inline-flex items-center rounded bg-red-700 px-3 py-1.5 text-white hover:bg-red-800"
        on:click={() => startLogin()}
      >
        Sign in again
      </button>
    </div>
  </div>
{/if}
