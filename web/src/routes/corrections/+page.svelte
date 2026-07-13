<script lang="ts">
  import ContactCard from "$lib/components/support/ContactCard.svelte";
  import PolicySection from "$lib/components/support/PolicySection.svelte";
  import TrustPage from "$lib/components/support/TrustPage.svelte";
</script>

<TrustPage
  title="Corrections"
  description="How to report an error and how Smarter.Vote LLC reviews corrections."
  path="/corrections/"
>
  <PolicySection title="Report a possible error">
    <p>
      Include the page URL, candidate or contest, the specific statement at
      issue, and a reliable supporting source. Do not include sensitive personal
      information.
    </p>
  </PolicySection>
  <PolicySection title="What happens next">
    <p>
      Smarter.Vote LLC reviews the cited evidence and retains editorial control
      over the outcome. We may correct, clarify, add context, update sources, or
      determine that no change is warranted. Material updates should be
      reflected on the relevant page.
    </p>
    <p>
      We are a small early-stage organization and do not yet promise a response
      time, but election-sensitive and safety-related reports receive priority.
    </p>
  </PolicySection>
  <ContactCard
    subject="Correction report: [page or race]"
    label="Report a correction"
  />
</TrustPage>
