import type { Source } from "../../src/lib/types";

/**
 * Builds a deterministic Source object for e2e fixtures. Keeping this in one
 * place means every fixture race gets consistently-shaped sourcing without
 * repeating boilerplate in each fixture file.
 */
export function fixtureSource(
  id: string,
  overrides: Partial<Source> = {},
): Source {
  return {
    url: `https://example.com/e2e-sources/${id}`,
    type: "government",
    title: `Fixture Source — ${id}`,
    description: "Deterministic e2e fixture source; not a real citation.",
    last_accessed: "2026-06-01T00:00:00Z",
    is_fresh: false,
    ...overrides,
  };
}
