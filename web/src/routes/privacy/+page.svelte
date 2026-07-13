<script lang="ts">
  import ContactCard from "$lib/components/support/ContactCard.svelte";
  import PolicySection from "$lib/components/support/PolicySection.svelte";
  import TrustPage from "$lib/components/support/TrustPage.svelte";
</script>

<TrustPage
  title="Privacy"
  description="A plain-language description of how Smarter.Vote handles visitor and inquiry data."
  path="/privacy/"
>
  <PolicySection title="Data we handle">
    <p>
      The public site may receive ordinary technical request data and
      privacy-preserving traffic measurements. If you email us, Gmail processes
      the message and related account information. Please send only what is
      needed for your inquiry.
    </p>
  </PolicySection>
  <PolicySection title="Address lookup">
    <p>
      Address lookup sends the address directly from your browser to the U.S.
      Census Geocoder to identify a state and congressional district.
      Smarter.Vote does not send the address to its own server, place it in the
      page URL or analytics, or save it in browser storage. The derived state,
      district, and matched race IDs are kept in this tab's session storage so
      results survive a refresh. They are cleared when you search another
      address or close the tab. The Census Bureau handles the lookup under its
      own policies.
    </p>
  </PolicySection>
  <PolicySection title="Retention and access">
    <p>
      The Gmail inbox is initially limited to the Smarter.Vote LLC owner,
      protected with multi-factor authentication, and organized by inquiry type.
      Our working target is to delete inactive inquiry correspondence after 12
      months unless it is needed for an active matter, legal obligation,
      security, or bookkeeping.
    </p>
  </PolicySection>
  <PolicySection title="Your choices">
    <p>
      You can browse public research without an account. You may ask about,
      correct, or request deletion of personal information you sent us, subject
      to obligations that require retention.
    </p>
  </PolicySection>
  <ContactCard subject="Privacy request" label="Send a privacy request" />
</TrustPage>
