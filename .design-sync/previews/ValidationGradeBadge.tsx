import * as React from "react";
import { ValidationGradeBadge } from "@smartervote/design-system";

export function GradeSweep() {
  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
      <ValidationGradeBadge
        grade={{ grade: "A", score: 94, summary: "Comprehensive sourcing with strong cross-verification across issue stances." }}
      />
      <ValidationGradeBadge
        grade={{ grade: "B", score: 78, summary: "Well sourced with some gaps in donor disclosure." }}
      />
      <ValidationGradeBadge
        grade={{ grade: "C", score: 61, summary: "Adequate coverage, but several stances rely on a single secondary source." }}
      />
      <ValidationGradeBadge
        grade={{ grade: "D", score: 44, summary: "Sparse sourcing on voting record; primary sources largely unavailable." }}
      />
      <ValidationGradeBadge
        grade={{ grade: "F", score: 22, summary: "Insufficient verifiable data to support most claims in this profile." }}
      />
    </div>
  );
}

export function InCandidateHeader() {
  return (
    <div style={{ maxWidth: 480, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
      <div>
        <div style={{ fontWeight: 700, fontSize: 18, color: "#111827" }}>Sarah Whitfield</div>
        <div style={{ fontSize: 13, color: "#6b7280" }}>Democrat · Georgia Senate 2026</div>
      </div>
      <ValidationGradeBadge grade={{ grade: "B", score: 82, summary: "Well sourced with some gaps in donor disclosure." }} />
    </div>
  );
}

export function DarkBackground() {
  return (
    <div
      className="dark"
      style={{ background: "#030712", padding: 20, borderRadius: 12, display: "flex", gap: 12, flexWrap: "wrap" }}
    >
      <ValidationGradeBadge
        grade={{ grade: "A", score: 91, summary: "Comprehensive sourcing with strong cross-verification." }}
      />
      <ValidationGradeBadge
        grade={{ grade: "C", score: 58, summary: "Adequate coverage, but several stances rely on a single source." }}
      />
    </div>
  );
}
