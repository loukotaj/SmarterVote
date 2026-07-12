<script lang="ts">
  import ContactCard from "$lib/components/support/ContactCard.svelte";
  import PolicySection from "$lib/components/support/PolicySection.svelte";
  import TrustPage from "$lib/components/support/TrustPage.svelte";
</script>

<TrustPage
  title="Support Smarter.Vote"
  description="Help Smarter.Vote LLC build broader, dependable election coverage."
  path="/support/"
>
  <div
    class="rounded-xl border border-amber-300 bg-amber-50 p-5 text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
    role="status"
  >
    <strong>Payments are not open yet.</strong> Smarter.Vote LLC is finishing its
    business, banking, bookkeeping, and policy setup before accepting support.
  </div>
  <PolicySection title="What support will enable">
    <p>
      Funding can help pay for election-data access, research, source review,
      accessibility, hosting, and expansion beyond national races. Until
      dependable provider coverage is affordable and validated, we will not
      imply complete state or local ballot coverage.
    </p>
  </PolicySection>
  <PolicySection title="Planned contribution terms">
    <p>
      Future support will be accepted by Smarter.Vote LLC. It will not be
      tax-deductible. Any choice about a geography or program will be treated as
      a nonbinding preference, not a legally or accountingly restricted fund,
      unless a written agreement explicitly says otherwise.
    </p>
    <p>
      No contribution will buy favorable coverage, editorial review, access to
      unpublished findings, or control of research. Final checkout and refund
      terms will appear before payments open.
    </p>
  </PolicySection>
  <ContactCard
    subject="Notify me when Smarter.Vote support opens"
    label="Ask about supporting Smarter.Vote"
  />
</TrustPage>
