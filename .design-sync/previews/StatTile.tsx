import * as React from "react";
import { StatTile } from "@smartervote/design-system";

export function Default() {
  return <StatTile value="04" label="Days" />;
}

export function ElectionCountdownRow() {
  return (
    <div style={{ display: "flex", gap: 10 }}>
      <StatTile value="112" label="Days" variant="tile" size="sm" />
      <StatTile value="08" label="Hrs" variant="tile" size="sm" />
      <StatTile value="43" label="Mins" variant="tile" size="sm" />
      <StatTile value="19" label="Secs" variant="tile" size="sm" />
    </div>
  );
}

export function ImpactMetricsRow() {
  return (
    <div style={{ display: "flex", gap: 32 }}>
      <StatTile value="1,240+" label="Candidates researched" variant="bare" size="lg" />
      <StatTile value="386" label="Races covered" variant="bare" size="lg" />
      <StatTile value="50" label="States tracked" variant="bare" size="lg" />
    </div>
  );
}

export function TileVsBare() {
  return (
    <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
      <StatTile value="27" label="Days Left" variant="tile" size="lg" />
      <StatTile value="27" label="Days Left" variant="bare" size="lg" />
    </div>
  );
}
