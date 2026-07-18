<script lang="ts">
  import TrustPage from "$lib/components/support/TrustPage.svelte";
</script>

<TrustPage
  title="Checkout cancelled"
  description="Your checkout was cancelled — no payment was taken."
  path="/support/cancel/"
>
  <p class="text-content-muted">
    No payment was taken. You can <a
      href="/support/"
      class="text-primary-600 underline hover:text-primary-700 dark:text-primary-400"
      >return to the support page</a
    > whenever you're ready.
  </p>
</TrustPage>
