import * as React from "react";
import { EmptyState } from "@smartervote/design-system";

export function WithAction() {
  return (
    <div style={{ maxWidth: 420 }}>
      <EmptyState
        message="We haven't found any voting record information for this candidate yet. This could mean the candidate hasn't held public office or records aren't available."
        helpText="Know a reliable source? Submit a link and help make voter information more complete."
        action={{ label: "Help improve this data", href: "https://github.com/loukotaj/SmarterVote/issues/new" }}
      />
    </div>
  );
}

export function MessageOnly() {
  return (
    <div style={{ maxWidth: 420 }}>
      <EmptyState message="We haven't found this information for this candidate yet." />
    </div>
  );
}
