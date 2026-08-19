import {
  getIssueDisplayName,
  type Candidate,
  type Race,
  type RaceSummary,
} from "$lib/types";
import { formatElectionDate } from "$lib/utils/electionDate";
import { canonicalRaceState } from "$lib/utils/states";

type TitleRace = Pick<Race | RaceSummary, "id"> &
  Partial<
    Pick<
      Race | RaceSummary,
      "title" | "office" | "state" | "jurisdiction" | "election_date"
    >
  > & {
    district?: string | null;
    candidates?: { name: string; withdrawn?: boolean }[];
  };

type MetadataCandidate = Pick<Candidate, "name"> &
  Partial<
    Pick<
      Candidate,
      | "issues"
      | "summary"
      | "summary_sources"
      | "career_history"
      | "education"
      | "donor_summary"
      | "voting_summary"
    >
  >;

function naturalList(values: string[]): string {
  if (values.length <= 1) return values[0] ?? "";
  if (values.length === 2) return `${values[0]} and ${values[1]}`;
  return `${values.slice(0, -1).join(", ")}, and ${values.at(-1)}`;
}

function cycleYear(race: TitleRace, parts: string[]): string | null {
  return (
    parts.find((part) => /^\d{4}$/.test(part)) ??
    race.election_date?.slice(0, 4) ??
    null
  );
}

function stateName(race: TitleRace): string | null {
  return canonicalRaceState(race);
}

function ordinal(value: string): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return value;
  const mod100 = number % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${number}th`;
  return `${number}${["th", "st", "nd", "rd"][number % 10] ?? "th"}`;
}

function houseDistrict(
  race: TitleRace,
  parts: string[],
  year: string,
): string | null {
  if (!parts.includes("house")) return null;
  const districtLabel = `${race.district ?? ""} ${race.jurisdiction ?? ""}`;
  if (/\bat[- ]large\b/i.test(districtLabel)) return "At-Large";
  const labeledDistrict = districtLabel.match(
    /\b(\d+)(?:st|nd|rd|th)?\s+(?:Congressional\s+)?District\b/i,
  );
  if (labeledDistrict) return ordinal(labeledDistrict[1]);
  if (parts.includes("at") && parts.includes("large")) return "At-Large";
  const numericDistrict = parts.find(
    (part) => /^\d{1,3}$/.test(part) && part !== year,
  );
  return numericDistrict ? ordinal(numericDistrict) : "At-Large";
}

/** A concise, deterministic election name for every public-facing race surface. */
export function raceDisplayTitle(race: TitleRace): string {
  const parts = race.id.toLowerCase().split("-");
  const year = cycleYear(race, parts);
  const state = stateName(race);
  const office = race.office?.toLowerCase() ?? "";
  const special = parts.includes("special") ? " Special" : "";

  if (year && state && office.includes("senate")) {
    return `${year} ${state} U.S. Senate${special} Election`;
  }
  if (
    year &&
    state &&
    (office.includes("house") || office.includes("representative"))
  ) {
    const district = houseDistrict(race, parts, year);
    if (district)
      return `${year} ${state}'s ${district} Congressional District${special} Election`;
  }
  if (
    year &&
    state &&
    (office.includes("governor") || office.includes("gubernatorial"))
  ) {
    if (office.includes("lieutenant governor")) {
      return `${year} ${state} Governor and Lieutenant Governor${special} Election`;
    }
    return `${year} ${state} Governor${special} Election`;
  }

  return race.title ?? race.office ?? "Election";
}

export function racePageTitle(race: TitleRace | null | undefined): string {
  if (!race) return "Loading... | Smarter.Vote";
  return `${raceDisplayTitle(race)} | Smarter.Vote`;
}

export function raceMetaDescription(
  race: TitleRace | null | undefined,
): string {
  const title = race ? raceDisplayTitle(race) : "this election";
  const activeNames =
    race?.candidates
      ?.filter((candidate) => !candidate.withdrawn)
      .map((candidate) => candidate.name)
      .filter(Boolean) ?? [];
  const candidateLabel =
    activeNames.length > 2
      ? `${activeNames[0]}, ${activeNames[1]}, and others`
      : naturalList(activeNames) || "candidates";
  const electionDate = race?.election_date
    ? ` on ${formatElectionDate(race.election_date)}`
    : "";

  return `Compare ${candidateLabel} in the ${title}${electionDate}, with sourced issue positions, polling, and race updates.`;
}

export function candidateMetaDescription(
  candidate: MetadataCandidate | null | undefined,
  race: TitleRace | null | undefined,
): string {
  const candidateName = candidate?.name ?? "this candidate";
  const title = race ? raceDisplayTitle(race) : "this election";
  if (!candidate) return `Explore ${candidateName}'s profile for the ${title}.`;

  const issueNames = Object.entries(candidate.issues ?? {})
    .filter(([, issue]) => {
      const stance = issue?.stance?.trim().toLowerCase() ?? "";
      return Boolean(
        stance &&
          !stance.includes("no public position found") &&
          !stance.includes("no publicly stated position"),
      );
    })
    .map(([issue]) => getIssueDisplayName(issue))
    .slice(0, 2);
  const details: string[] = [];

  if (issueNames.length > 0) {
    details.push(`positions on ${naturalList(issueNames)}`);
  }
  if (
    candidate.summary?.trim() ||
    candidate.career_history?.length ||
    candidate.education?.length
  ) {
    details.push("biography");
  }
  if (candidate.donor_summary?.trim()) details.push("donor information");
  if (candidate.voting_summary?.trim()) details.push("voting record");
  if (
    candidate.summary_sources?.length ||
    Object.values(candidate.issues ?? {}).some(
      (issue) => (issue?.sources?.length ?? 0) > 0,
    )
  ) {
    details.push("cited sources");
  }

  if (details.length === 0) {
    return `Learn about ${candidateName} in the ${title}.`;
  }
  return `Explore ${candidateName}'s ${naturalList(details)} for the ${title}.`;
}
