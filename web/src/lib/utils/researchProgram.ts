import type { ResearchManifestEntry } from "$lib/types";

export interface ResearchEventChoice {
  key: string;
  kind: "Primary" | "Runoff" | "General";
  eventType: string;
  eventDate: string;
}

export function researchEventChoices(
  manifest: ResearchManifestEntry,
): ResearchEventChoice[] {
  const choices: ResearchEventChoice[] = [];
  if (manifest.primary_date) {
    choices.push({
      key: `primary|${manifest.primary_date}`,
      kind: "Primary",
      eventType: manifest.event_type,
      eventDate: manifest.primary_date,
    });
  }
  if (manifest.runoff_date) {
    choices.push({
      key: `runoff|${manifest.runoff_date}`,
      kind: "Runoff",
      eventType:
        manifest.event_type === "open_primary"
          ? "open_primary_runoff"
          : "primary_runoff",
      eventDate: manifest.runoff_date,
    });
  }
  if (
    !choices.some(
      (choice) => choice.eventDate === manifest.general_election_date,
    )
  ) {
    choices.push({
      key: `general|${manifest.general_election_date}`,
      kind: "General",
      eventType: manifest.primary_date
        ? "general_election"
        : manifest.event_type,
      eventDate: manifest.general_election_date,
    });
  }
  return choices;
}
