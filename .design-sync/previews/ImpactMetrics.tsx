import * as React from "react";
import { ImpactMetrics } from "@smartervote/design-system";

/** Current published coverage snapshot, mid-cycle. */
export function Default() {
  return (
    <div style={{ width: 1000 }}>
      <ImpactMetrics
        metrics={{
          guides: 128,
          candidateProfiles: 512,
          statesRepresented: 34,
          lastUpdated: "2026-07-10",
          snapshotDate: "2026-07-11",
        }}
      />
    </div>
  );
}

/** Larger coverage numbers later in the cycle, showing all four stats scale cleanly. */
export function LargerCoverage() {
  return (
    <div style={{ width: 1000 }}>
      <ImpactMetrics
        metrics={{
          guides: 342,
          candidateProfiles: 1875,
          statesRepresented: 50,
          lastUpdated: "2026-06-30",
          snapshotDate: "2026-07-01",
        }}
      />
    </div>
  );
}
