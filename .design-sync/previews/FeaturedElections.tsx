import * as React from "react";
import { FeaturedElections } from "@smartervote/design-system";

const fiveRaces = [
  {
    id: "ga-senate-2026",
    title: "Georgia U.S. Senate",
    jurisdiction: "Georgia",
    updatedUtc: "2026-07-10T14:30:00Z",
    candidates: [{ name: "Alice Johnson" }, { name: "Marcus Webb" }, { name: "Diane Foster" }],
  },
  {
    id: "mi-governor-2026",
    title: "Michigan Governor",
    jurisdiction: "Michigan",
    updatedUtc: "2026-07-09T09:15:00Z",
    candidates: [{ name: "Bob Lee" }, { name: "Nina Torres" }],
  },
  {
    id: "az-house-06-2026",
    office: "U.S. House, District 6",
    jurisdiction: "Arizona",
    updatedUtc: "2026-07-08T11:00:00Z",
    candidates: [{ name: "Carlos Mendez" }, { name: "Sarah Kim" }, { name: "James Patel" }],
  },
  {
    id: "tx-ag-2026",
    title: "Texas Attorney General",
    jurisdiction: "Texas",
    updatedUtc: "2026-07-07T16:45:00Z",
    candidates: [{ name: "Laura Chen" }, { name: "Tom Rivera" }],
  },
  {
    id: "nc-senate-2026",
    title: "North Carolina U.S. Senate",
    jurisdiction: "North Carolina",
    updatedUtc: "2026-07-06T08:00:00Z",
    candidates: [{ name: "Grace Kim" }, { name: "Ethan Brooks" }],
  },
];

/** Full editorial layout: one large featured story plus a four-item side list. */
export function FiveRaces() {
  return (
    <div style={{ width: 620 }}>
      <FeaturedElections races={fiveRaces} />
    </div>
  );
}

/** Minimal-but-valid state: only the featured race exists yet, so the side list is empty. */
export function SingleRaceFeaturedOnly() {
  return (
    <div style={{ width: 620 }}>
      <FeaturedElections races={[fiveRaces[0]]} />
    </div>
  );
}

/** Featured race has no `title`, so the headline falls back to `office`. */
export function OfficeFallbackFeatured() {
  const races = [
    {
      id: "az-house-06-2026",
      office: "U.S. House, District 6",
      jurisdiction: "Arizona",
      updatedUtc: "2026-07-08T11:00:00Z",
      candidates: [{ name: "Carlos Mendez" }, { name: "Sarah Kim" }, { name: "James Patel" }],
    },
    ...fiveRaces.slice(1),
  ];
  return (
    <div style={{ width: 620 }}>
      <FeaturedElections races={races} />
    </div>
  );
}
