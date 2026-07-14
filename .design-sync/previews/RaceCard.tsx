import * as React from "react";
import { RaceCard } from "@smartervote/design-system";

export function USSenateRace() {
  return (
    <div style={{ maxWidth: 340 }}>
      <RaceCard
        race={{
          id: "ga-senate-2026",
          office: "US Senate",
          jurisdiction: "Georgia",
          electionDate: "2026-11-03",
          candidates: [
            { name: "Alice Johnson", party: "democrat" },
            { name: "Marcus Webb", party: "republican" },
          ],
        }}
      />
    </div>
  );
}

export function GovernorRaceWithThirdParty() {
  return (
    <div style={{ maxWidth: 340 }}>
      <RaceCard
        race={{
          id: "oh-governor-2026",
          office: "Governor",
          jurisdiction: "Ohio",
          electionDate: "2026-11-03",
          candidates: [
            { name: "Renee Castillo", party: "democrat" },
            { name: "Dale Turner", party: "republican" },
            { name: "Priya Nandakumar", party: "independent" },
          ],
        }}
      />
    </div>
  );
}

export function USHouseRace() {
  return (
    <div style={{ maxWidth: 340 }}>
      <RaceCard
        race={{
          id: "tx-house-12-2026",
          title: "US House — Texas District 12",
          office: "US House",
          jurisdiction: "Texas District 12",
          electionDate: "2026-11-03",
          candidates: [
            { name: "Bob Lee", party: "republican" },
            { name: "Karen Osei", party: "democrat" },
          ],
        }}
      />
    </div>
  );
}

export function SecretaryOfStateRace() {
  return (
    <div style={{ maxWidth: 340 }}>
      <RaceCard
        race={{
          id: "az-secretary-of-state-2026",
          office: "Secretary of State",
          jurisdiction: "Arizona",
          electionDate: "2026-11-03",
          candidates: [
            { name: "Grace Whitfield", party: "democrat" },
            { name: "Sam Delgado", party: "republican" },
          ],
        }}
      />
    </div>
  );
}

export function AttorneyGeneralRace() {
  return (
    <div style={{ maxWidth: 340 }}>
      <RaceCard
        race={{
          id: "mi-attorney-general-2026",
          office: "Attorney General",
          jurisdiction: "Michigan",
          electionDate: "2026-11-03",
          candidates: [
            { name: "Nathaniel Reyes", party: "democrat" },
            { name: "Louise Farrow", party: "republican" },
            { name: "Ethan Park", party: "libertarian" },
          ],
        }}
      />
    </div>
  );
}

export function NoJurisdictionFallbackTitle() {
  return (
    <div style={{ maxWidth: 340 }}>
      <RaceCard
        race={{
          id: "special-election-2026",
          office: "US Senate",
          electionDate: "2026-01-20",
          candidates: [
            { name: "Owen Marsh", party: "democrat" },
            { name: "Vivian Cho", party: "republican" },
          ],
        }}
      />
    </div>
  );
}
