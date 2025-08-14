<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { getAuth0Client } from "$lib/auth";

  let ready = false;

  onMount(async () => {
    const auth0 = await getAuth0Client();

    if (window.location.search.includes("code=")) {
      await auth0.handleRedirectCallback();
      goto("/admin/pipeline");
    } else if (await auth0.isAuthenticated()) {
      goto("/admin/pipeline");
    } else {
      ready = true;
    }
  });

  async function login() {
    const auth0 = await getAuth0Client();
    await auth0.loginWithRedirect();
  }
</script>

{#if ready}
  <div class="flex items-center justify-center min-h-screen">
    <button on:click={login} class="btn-primary">Login with Auth0</button>
  </div>
{/if}
