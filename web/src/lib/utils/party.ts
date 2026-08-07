/** Shared party-related display utilities.
 *
 * Every helper here classifies the same free-text party string, so they all go
 * through `partyKey` rather than each carrying its own ladder of checks. They
 * used to, and they disagreed: an independent got a purple badge from
 * `partyBadgeClass` and a grey ring from `partyRing`, because only two of the
 * four had learned about independents. That is a visible mismatch on the
 * candidates who least fit the two-party assumption — Alaska, Maine and Vermont
 * all field them — and adding a party meant remembering four places.
 */

/** Canonical bucket for a free-text party label. */
export type PartyKey = "dem" | "rep" | "ind" | "grn" | "lib" | "other";

export function partyKey(party: string | undefined): PartyKey {
  const p = (party || "").toLowerCase().trim();
  if (!p) return "other";
  if (p.includes("democrat") || p === "d" || p === "dfl") return "dem";
  if (p.includes("republican") || p === "r" || p === "gop") return "rep";
  if (p.includes("independent") || p === "i") return "ind";
  if (p.includes("green") || p === "g") return "grn";
  if (p.includes("libertarian") || p === "l") return "lib";
  return "other";
}

const ABBR: Record<PartyKey, string | null> = {
  dem: "D",
  rep: "R",
  ind: "I",
  grn: "G",
  lib: "L",
  other: null,
};

/** Abbreviated party label (D, R, I, L, G, etc.). */
export function partyAbbr(party: string | undefined): string {
  if (!party) return "?";
  return ABBR[partyKey(party)] ?? party[0].toUpperCase();
}

const BADGE_CLASS: Record<PartyKey, string> = {
  dem: "bg-blue-100 dark:bg-blue-950/70 text-blue-800 dark:text-blue-200 border border-blue-200/60 dark:border-blue-800/60",
  rep: "bg-red-100 dark:bg-red-950/70 text-red-800 dark:text-red-200 border border-red-200/60 dark:border-red-800/60",
  ind: "bg-purple-100 dark:bg-purple-950/70 text-purple-800 dark:text-purple-200 border border-purple-200/60 dark:border-purple-800/60",
  grn: "bg-emerald-100 dark:bg-emerald-950/70 text-emerald-800 dark:text-emerald-200 border border-emerald-200/60 dark:border-emerald-800/60",
  lib: "bg-amber-100 dark:bg-amber-950/70 text-amber-900 dark:text-amber-200 border border-amber-200/60 dark:border-amber-800/60",
  other:
    "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-stroke/50",
};

/** Tailwind badge classes for a party pill (bg + text, light & dark). */
export function partyBadgeClass(party: string | undefined): string {
  if (!party) return BADGE_CLASS.other;
  return BADGE_CLASS[partyKey(party)];
}

const RING_CLASS: Record<PartyKey, string> = {
  dem: "ring-blue-500",
  rep: "ring-red-500",
  ind: "ring-purple-500",
  grn: "ring-green-500",
  lib: "ring-yellow-500",
  other: "ring-gray-400",
};

/** Tailwind ring color for avatar borders. */
export function partyRing(party: string | undefined): string {
  // An absent party is not the same as an unrecognised one: nothing is claimed,
  // so the avatar stays lighter than a party we simply have no colour for.
  if (!party) return "ring-gray-300";
  return RING_CLASS[partyKey(party)];
}

const INITIAL_BG_CLASS: Record<PartyKey, string> = {
  dem: "bg-blue-500",
  rep: "bg-red-500",
  ind: "bg-purple-500",
  grn: "bg-green-500",
  lib: "bg-yellow-500",
  other: "bg-gray-500",
};

/** Tailwind background for the initial-letter fallback avatar. */
export function partyInitialBg(party: string | undefined): string {
  if (!party) return "bg-gray-400";
  return INITIAL_BG_CLASS[partyKey(party)];
}

/**
 * Short CSS class token used for poll bars etc. (dem/rep/empty).
 *
 * Deliberately only D and R: the race page styles `.poll-bar-fill.dem` and
 * `.poll-bar-fill.rep` and nothing else, so any other key would name a class
 * that does not exist. A third-party candidate's bar takes the default fill.
 */
export function partySlug(party: string | undefined): string {
  const key = partyKey(party);
  return key === "dem" || key === "rep" ? key : "";
}
