import * as React from "react";
import { Badge } from "../Badge";
import { Avatar } from "../Avatar";
import { partyAbbr, partyRing } from "../../utils/party";

export interface RaceCardCandidate {
  name: string;
  party?: string;
  imageUrl?: string;
}

export interface RaceCardData {
  id: string;
  title?: string;
  office?: string;
  jurisdiction?: string;
  electionDate: string;
  candidates: RaceCardCandidate[];
}

export interface RaceCardProps {
  race: RaceCardData;
  /** Link target. Defaults to "/races/{race.id}". */
  href?: string;
}

function officeBadge(office?: string): { label: string; tone: React.ComponentProps<typeof Badge>["tone"] } {
  if (!office) return { label: "Race", tone: "gray" };
  const o = office.toLowerCase();
  if (o.includes("senate")) return { label: "Senate", tone: "blue" };
  if (o.includes("governor") || o.includes("gubernatorial")) return { label: "Governor", tone: "purple" };
  if (o.includes("house") || o.includes("representative")) return { label: "House", tone: "indigo" };
  if (o.includes("secretary")) return { label: "Sec. of State", tone: "teal" };
  if (o.includes("attorney")) return { label: "Atty. General", tone: "orange" };
  return { label: office.length > 22 ? office.slice(0, 22) + "…" : office, tone: "gray" };
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/**
 * Race summary card — office/jurisdiction badges, title, a row of
 * candidate avatars (party-ring colored), and a "View race" footer link.
 * The election-directory grid is built from a list of these.
 */
export function RaceCard({ race, href = `/races/${race.id}` }: RaceCardProps) {
  const badge = officeBadge(race.office);

  return (
    <a
      href={href}
      className="group block bg-surface rounded-xl border border-stroke hover:border-blue-400 hover:shadow-md transition-all duration-200 overflow-hidden"
    >
      <div className="px-4 pt-4 pb-3 flex flex-wrap items-center gap-2">
        <Badge tone={badge.tone} size="sm">
          {badge.label}
        </Badge>
        {race.jurisdiction && (
          <Badge tone="green" size="sm">
            {race.jurisdiction}
          </Badge>
        )}
        <span className="ml-auto text-xs text-content-subtle whitespace-nowrap">{formatDate(race.electionDate)}</span>
      </div>

      <div className="px-4 pb-3">
        <h3 className="text-sm font-semibold text-content group-hover:text-blue-600 transition-colors leading-snug line-clamp-2 capitalize">
          {race.title ?? `${race.office ?? "Race"} — ${race.jurisdiction ?? ""}`}
        </h3>
      </div>

      <div className="px-4 pb-3">
        <div className="flex flex-wrap gap-3">
          {race.candidates.map((candidate) => (
            <div key={candidate.name} className="flex items-center gap-2 min-w-0">
              <Avatar name={candidate.name} src={candidate.imageUrl} size="sm" className={`ring-2 ${partyRing(candidate.party)}`} />
              <div className="min-w-0">
                <p className="text-xs font-medium text-content truncate max-w-[110px]">{candidate.name}</p>
                {candidate.party && <p className="text-xs text-content-subtle">{partyAbbr(candidate.party)}</p>}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="px-4 py-2.5 border-t border-stroke flex items-center justify-end gap-1 text-xs font-medium text-blue-500 dark:text-blue-400">
        View race
        <svg
          className="w-3.5 h-3.5 transition-transform duration-150 group-hover:translate-x-0.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
        </svg>
      </div>
    </a>
  );
}
