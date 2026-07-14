import * as React from "react";
import { Button } from "@smartervote/design-system";

export function VariantSweep() {
  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
      <Button variant="primary">View Race</Button>
      <Button variant="secondary">Cancel</Button>
      <Button variant="outline">Compare Candidates</Button>
      <Button variant="pill">All Issues</Button>
      <Button variant="danger">Retire Race</Button>
    </div>
  );
}

export function Sizes() {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <Button variant="primary" size="sm">
        Explore
      </Button>
      <Button variant="primary" size="md">
        Explore
      </Button>
      <Button variant="primary" size="lg">
        Explore
      </Button>
    </div>
  );
}

export function PillFilterRow() {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      <Button variant="pill" active>
        All Races
      </Button>
      <Button variant="pill">Senate</Button>
      <Button variant="pill">Governor</Button>
      <Button variant="pill">House</Button>
      <Button variant="pill">Ballot Measures</Button>
    </div>
  );
}

export function DisabledState() {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <Button variant="primary" disabled>
        Publish Race
      </Button>
      <Button variant="outline" disabled>
        Regenerate Forecast
      </Button>
    </div>
  );
}

export function CallToActionExample() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 320 }}>
      <p style={{ margin: 0, fontSize: 14, color: "#374151" }}>
        Georgia U.S. Senate — 2026 general election
      </p>
      <div style={{ display: "flex", gap: 8 }}>
        <Button variant="primary" size="md">
          View Full Race Guide
        </Button>
        <Button variant="secondary" size="md">
          Share
        </Button>
      </div>
    </div>
  );
}
