/** Shared party-related display utilities — ported verbatim from web/src/lib/utils/party.ts. */

function isDem(p: string): boolean {
  return p.includes("democrat") || p === "d" || p === "dfl";
}

function isRep(p: string): boolean {
  return p.includes("republican") || p === "r" || p === "gop";
}

function isLib(p: string): boolean {
  return p.includes("libertarian") || p === "l";
}

function isGreen(p: string): boolean {
  return p.includes("green") || p === "g";
}

/** Abbreviated party label (D, R, I, L, G, etc.). */
export function partyAbbr(party: string | undefined): string {
  if (!party) return "?";
  const p = party.toLowerCase();
  if (isDem(p)) return "D";
  if (isRep(p)) return "R";
  if (p.includes("independent") || p === "i") return "I";
  if (isGreen(p)) return "G";
  if (isLib(p)) return "L";
  return party[0].toUpperCase();
}

/** Tailwind ring color for avatar borders. */
export function partyRing(party: string | undefined): string {
  if (!party) return "ring-gray-300";
  const p = party.toLowerCase();
  if (isDem(p)) return "ring-blue-500";
  if (isRep(p)) return "ring-red-500";
  if (isGreen(p)) return "ring-green-500";
  if (isLib(p)) return "ring-yellow-500";
  return "ring-gray-400";
}

/** Tailwind background for the initial-letter fallback avatar. */
export function partyInitialBg(party: string | undefined): string {
  if (!party) return "bg-gray-400";
  const p = party.toLowerCase();
  if (isDem(p)) return "bg-blue-500";
  if (isRep(p)) return "bg-red-500";
  if (isGreen(p)) return "bg-green-500";
  if (isLib(p)) return "bg-yellow-500";
  return "bg-gray-500";
}
