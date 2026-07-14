import * as React from "react";
import { SourceLink } from "@smartervote/design-system";

export function DomainFallback() {
  return <SourceLink url="https://ballotpedia.org/Alice_Johnson" />;
}

export function WithTitle() {
  return <SourceLink url="https://ballotpedia.org/Alice_Johnson" title="Alice Johnson — Ballotpedia" />;
}

export function ExplicitLabel() {
  return (
    <SourceLink
      url="https://www.johnsonforsenate.com/issues/healthcare"
      title="Johnson for Senate — Healthcare Policy"
      text="Campaign healthcare platform"
    />
  );
}

export function NonHttpFallback() {
  return <SourceLink url="Georgia Secretary of State, official candidate filing (paper record)" />;
}

export function SourceListInContext() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 360 }}>
      <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: "#374151" }}>Sources</p>
      <SourceLink url="https://ballotpedia.org/Alice_Johnson" title="Alice Johnson — Ballotpedia" />
      <SourceLink url="https://www.johnsonforsenate.com" title="Johnson for Senate — official site" />
      <SourceLink url="https://example.gov/elections/2026/candidate-filings" text="GA Secretary of State filing" />
    </div>
  );
}
