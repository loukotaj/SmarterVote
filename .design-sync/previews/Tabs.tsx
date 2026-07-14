import * as React from "react";
import { Tabs } from "@smartervote/design-system";

const candidateTabItems = [
  { value: "issues", label: "Issues" },
  { value: "background", label: "Background" },
  { value: "donors", label: "Donors" },
  { value: "voting", label: "Voting Record" },
];

export function IssuesActive() {
  return (
    <div style={{ maxWidth: 480 }}>
      <Tabs items={candidateTabItems} value="issues" onChange={() => {}} />
    </div>
  );
}

export function DonorsActive() {
  return (
    <div style={{ maxWidth: 480 }}>
      <Tabs items={candidateTabItems} value="donors" onChange={() => {}} />
    </div>
  );
}

export function WithDisabledTab() {
  const items = [
    { value: "overview", label: "Overview" },
    { value: "polling", label: "Polling" },
    { value: "endorsements", label: "Endorsements", disabled: true },
    { value: "history", label: "Voting Record" },
  ];
  return (
    <div style={{ maxWidth: 520 }}>
      <Tabs items={items} value="polling" onChange={() => {}} />
    </div>
  );
}

export function DarkBackground() {
  return (
    <div className="dark" style={{ background: "#030712", padding: 20, borderRadius: 12, maxWidth: 480 }}>
      <Tabs items={candidateTabItems} value="background" onChange={() => {}} />
    </div>
  );
}
