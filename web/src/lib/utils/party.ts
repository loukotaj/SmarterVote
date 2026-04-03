/** Shared party-related display utilities. */

/** Abbreviated party label (D, R, I, L, G, etc.). */
export function partyAbbr(party: string | undefined): string {
  if (!party) return "?";
  const p = party.toLowerCase();
  if (p.includes("democrat")) return "D";
  if (p.includes("republican")) return "R";
  if (p.includes("independent")) return "I";
  if (p.includes("green")) return "G";
  if (p.includes("libertarian")) return "L";
  return party[0].toUpperCase();
}

/** Tailwind badge classes for a party pill (bg + text, light & dark). */
export function partyBadgeClass(party: string | undefined): string {
  if (!party) return "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300";
  const p = party.toLowerCase();
  if (p.includes("democrat")) return "bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200";
  if (p.includes("republican")) return "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200";
  if (p.includes("libertarian")) return "bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200";
  if (p.includes("green")) return "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200";
  return "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300";
}

/** Tailwind ring color for avatar borders. */
export function partyRing(party: string | undefined): string {
  if (!party) return "ring-gray-300";
  const p = party.toLowerCase();
  if (p.includes("democrat")) return "ring-blue-500";
  if (p.includes("republican")) return "ring-red-500";
  if (p.includes("green")) return "ring-green-500";
  if (p.includes("libertarian")) return "ring-yellow-500";
  return "ring-gray-400";
}

/** Tailwind background for the initial-letter fallback avatar. */
export function partyInitialBg(party: string | undefined): string {
  if (!party) return "bg-gray-400";
  const p = party.toLowerCase();
  if (p.includes("democrat")) return "bg-blue-500";
  if (p.includes("republican")) return "bg-red-500";
  if (p.includes("green")) return "bg-green-500";
  if (p.includes("libertarian")) return "bg-yellow-500";
  return "bg-gray-500";
}

/** Short CSS class token used for poll bars etc. (dem/rep/empty). */
export function partySlug(party: string | undefined): string {
  if (!party) return "";
  const p = party.toLowerCase();
  if (p.includes("democrat")) return "dem";
  if (p.includes("republican")) return "rep";
  return "";
}
