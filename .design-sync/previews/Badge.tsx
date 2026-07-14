import * as React from "react";
import { Badge } from "@smartervote/design-system";

export function ToneSweep() {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      <Badge tone="gray">Race</Badge>
      <Badge tone="blue">Senate</Badge>
      <Badge tone="green">A</Badge>
      <Badge tone="yellow">C</Badge>
      <Badge tone="orange">Atty. General</Badge>
      <Badge tone="red">F</Badge>
      <Badge tone="purple">Governor</Badge>
      <Badge tone="teal">Sec. of State</Badge>
      <Badge tone="indigo">House</Badge>
    </div>
  );
}

export function Sizes() {
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
      <Badge tone="blue" size="sm">
        GA
      </Badge>
      <Badge tone="blue" size="md">
        Senate
      </Badge>
    </div>
  );
}

export function InContext() {
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      <Badge tone="gray" size="sm">
        Independent
      </Badge>
      <Badge tone="green" size="sm">
        Incumbent
      </Badge>
    </div>
  );
}
