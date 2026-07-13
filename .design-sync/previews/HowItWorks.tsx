import * as React from "react";
import { HowItWorks } from "@smartervote/design-system";

/** Built-in defaults: eyebrow, heading, and the three-step "Find / Compare / Inspect" copy. */
export function Default() {
  return (
    <div style={{ width: 620 }}>
      <HowItWorks />
    </div>
  );
}

/** Custom heading and step content, showing the section adapts to a different explainer. */
export function CustomSteps() {
  return (
    <div style={{ width: 620 }}>
      <HowItWorks
        eyebrow="Before you vote"
        heading="Four steps to an informed ballot."
        steps={[
          { title: "Locate", description: "Enter your address to see every race on your ballot." },
          { title: "Read", description: "Review each candidate's positions on the twelve canonical issues." },
          { title: "Verify", description: "Follow citations back to campaign sites, filings, and news coverage." },
          { title: "Decide", description: "Compare candidates side by side before you cast your vote." },
        ]}
      />
    </div>
  );
}
