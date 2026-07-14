import * as React from "react";
import { CandidateCard } from "@smartervote/design-system";

const alice = {
  name: "Alice Johnson",
  party: "democrat",
  incumbent: true,
  summary:
    "Alice Johnson has served two terms in the state senate, focusing on healthcare access, infrastructure investment, and public education funding across rural and urban districts alike.",
  websiteUrl: "https://example.com",
  issues: [
    { issue: "Healthcare", stance: "Supports expanding Medicaid eligibility and lowering prescription drug costs.", confidence: "high" as const },
    { issue: "Economy", stance: "Backs targeted small-business tax credits and infrastructure spending.", confidence: "medium" as const },
    { issue: "Education", stance: "Proposes increased per-pupil funding for public schools.", confidence: "high" as const },
  ],
  careerHistory: [
    { title: "State Senator", organization: "State Senate, District 14", startYear: 2018, description: "Chaired the Health & Human Services Committee." },
    { title: "City Council Member", organization: "Springfield City Council", startYear: 2012, endYear: 2018 },
  ],
  education: [{ institution: "State University", degree: "B.A.", field: "Political Science", year: 2008 }],
};

export function Collapsed() {
  return (
    <div style={{ maxWidth: 480 }}>
      <CandidateCard candidate={alice} href="/races/ga-senate-2026/alice-johnson" />
    </div>
  );
}

export function ExpandedWithIssues() {
  return (
    <div style={{ maxWidth: 520 }}>
      <CandidateCard candidate={alice} href="/races/ga-senate-2026/alice-johnson" defaultExpanded />
    </div>
  );
}

export function NoPhotoNoIssuesYet() {
  return (
    <div style={{ maxWidth: 480 }}>
      <CandidateCard
        candidate={{ name: "Bob Lee", party: "republican", summary: "Bob Lee is a small-business owner running for the first time." }}
        defaultExpanded
      />
    </div>
  );
}

export function SelectableForComparison() {
  return (
    <div style={{ display: "flex", gap: 16 }}>
      <div style={{ maxWidth: 300 }}>
        <CandidateCard candidate={alice} selectable selected />
      </div>
      <div style={{ maxWidth: 300 }}>
        <CandidateCard candidate={{ name: "Bob Lee", party: "republican" }} selectable selected={false} />
      </div>
    </div>
  );
}
