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
      Address lookup is not available today. If introduced, its intended design
      is to use an address only to identify election districts, avoid putting
      addresses in URLs or analytics, and keep refresh state in the browser
      session rather than a Smarter.Vote server record. This policy will be
      updated before launch with the applicable providers and retention details.
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
