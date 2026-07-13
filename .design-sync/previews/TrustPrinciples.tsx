import * as React from "react";
import { TrustPrinciples } from "@smartervote/design-system";

/** Built-in defaults: the three-principle "editorial promise" copy. Always dark (bg-blue-950), regardless of page theme. */
export function Default() {
  return (
    <div style={{ width: 1000 }}>
      <TrustPrinciples />
    </div>
  );
}

/** Custom eyebrow, heading, description, CTA, and a four-principle override. */
export function CustomPrinciples() {
  return (
    <div style={{ width: 1000 }}>
      <TrustPrinciples
        eyebrow="How we work"
        heading="Verify everything yourself."
        description="Every figure on this site traces back to a primary source you can open and read."
        ctaHref="/about/#sources"
        ctaLabel="Read our sourcing standards →"
        principles={[
          { number: "01", title: "Primary sources first", description: "Campaign filings, voting records, and official statements outrank secondhand summaries." },
          { number: "02", title: "Multiple models, one record", description: "Independent AI reviewers cross-check research before it's published." },
          { number: "03", title: "Corrections are public", description: "When a claim is wrong, the fix and the reason are logged in the open." },
          { number: "04", title: "Nonpartisan by design", description: "Every candidate on a ballot gets the same research treatment." },
        ]}
      />
    </div>
  );
}
