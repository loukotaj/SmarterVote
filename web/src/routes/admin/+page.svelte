<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { getAuth0Client } from "$lib/auth";

  onMount(async () => {
    const auth0 = await getAuth0Client();
    if (window.location.search.includes("code=")) {
      await auth0.handleRedirectCallback();
      goto("/admin/pipeline");
    } else if (await auth0.isAuthenticated()) {
      goto("/admin/pipeline");
    } else {
      await auth0.loginWithRedirect();
    }
  });
</script>
