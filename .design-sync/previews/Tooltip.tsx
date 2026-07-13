import * as React from "react";
import { Tooltip } from "@smartervote/design-system";

export function Closed() {
  return (
    <Tooltip trigger={<span style={{ color: "#2563eb", cursor: "pointer", fontWeight: 600 }}>Validation info</span>}>
      <p style={{ fontSize: 14, color: "#111827" }}>
        Multiple AI models independently review each race profile for factual accuracy and neutrality.
      </p>
    </Tooltip>
  );
}

export function RightAligned() {
  return (
    <div style={{ display: "flex", justifyContent: "flex-end" }}>
      <Tooltip
        align="right"
        trigger={
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "#4b5563", cursor: "pointer" }}>
            ⓘ Renamed issue
          </span>
        }
      >
        <p style={{ fontSize: 13, color: "#4b5563" }}>
          This issue was previously labeled "Economy" and was renamed to "Economic Policy" in a later research pass.
        </p>
      </Tooltip>
    </div>
  );
}
