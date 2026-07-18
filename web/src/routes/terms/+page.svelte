<script lang="ts">
  import ContactCard from "$lib/components/support/ContactCard.svelte";
  import PolicySection from "$lib/components/support/PolicySection.svelte";
  import TrustPage from "$lib/components/support/TrustPage.svelte";
</script>

<TrustPage
  title="Terms of use"
  description="The basic terms for using Smarter.Vote's public election research."
  path="/terms/"
>
  <PolicySection title="Informational service">
    <p>
      Smarter.Vote provides general civic information. It is not an official
      election authority, legal advice, a complete ballot, or a substitute for
      checking government election resources. Content may contain errors,
      omissions, or outdated information.
    </p>
  </PolicySection>
  <PolicySection title="No endorsements or guarantees">
    <p>
      Smarter.Vote does not endorse candidates or parties. Forecasts and
      summaries are estimates and research aids, not promises of accuracy,
      outcomes, or fitness for a particular purpose. Use the service at your own
      discretion.
    </p>
  </PolicySection>
  <PolicySection title="Acceptable use and third parties">
    <p>
      Do not disrupt the service, bypass access controls, scrape it in a way
      that harms availability, or misrepresent Smarter.Vote content. Links and
      citations lead to third-party services with their own terms and privacy
      practices.
    </p>
  </PolicySection>
  <PolicySection title="Organization and changes">
    <p>
      The service is operated by Smarter.Vote LLC. We may update, suspend, or
      discontinue features and revise these terms as the service develops.
      Questions about charges, recurring support, cancellation, or refunds can
      be sent through the support page.
    </p>
  </PolicySection>
  <ContactCard subject="Terms question" />
</TrustPage>
