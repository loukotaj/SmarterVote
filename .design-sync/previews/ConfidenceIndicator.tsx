import * as React from "react";
import { ConfidenceIndicator } from "@smartervote/design-system";

export function LevelSweep() {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      <ConfidenceIndicator confidence="high" />
      <ConfidenceIndicator confidence="medium" />
      <ConfidenceIndicator confidence="low" />
      <ConfidenceIndicator confidence="unknown" />
    </div>
  );
}

export function InIssueStance() {
  return (
    <div style={{ maxWidth: 480, display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <span style={{ fontWeight: 600, fontSize: 14, color: "#111827" }}>Healthcare</span>
        <ConfidenceIndicator confidence="high" />
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <span style={{ fontWeight: 600, fontSize: 14, color: "#111827" }}>Immigration</span>
        <ConfidenceIndicator confidence="medium" />
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <span style={{ fontWeight: 600, fontSize: 14, color: "#111827" }}>Foreign Policy</span>
        <ConfidenceIndicator confidence="low" />
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <span style={{ fontWeight: 600, fontSize: 14, color: "#111827" }}>Housing</span>
        <ConfidenceIndicator confidence="unknown" />
      </div>
    </div>
  );
}

export function DarkBackground() {
  return (
    <div
      className="dark"
      style={{ background: "#030712", padding: 20, borderRadius: 12, display: "flex", gap: 8, flexWrap: "wrap" }}
    >
      <ConfidenceIndicator confidence="high" />
      <ConfidenceIndicator confidence="medium" />
      <ConfidenceIndicator confidence="low" />
      <ConfidenceIndicator confidence="unknown" />
    </div>
  );
}
