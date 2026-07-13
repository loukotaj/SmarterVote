export interface FeaturedElectionsRace {
  id: string;
  title?: string;
  office?: string;
  jurisdiction?: string;
  updatedUtc: string;
  candidates: { name: string }[];
}

export interface FeaturedElectionsProps {
  /** First race is the large "Featured" story; up to 4 more render as the side list. */
  races: FeaturedElectionsRace[];
}

function formatDate(date: string): string {
  return new Date(date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/**
 * Homepage "recently updated" editorial section — one large featured race
 * beside a compact list of the next few. Renders nothing when `races` is empty.
 */
export function FeaturedElections({ races }: FeaturedElectionsProps) {
  if (!races.length) return null;
  const [featured, ...rest] = races;
  const sideRaces = rest.slice(0, 4);

  return (
    <section className="border-t border-stroke py-20 sm:py-28" aria-labelledby="recent-elections">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <header className="flex items-end justify-between gap-6 border-b border-stroke pb-6">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.24em] text-blue-600 dark:text-blue-400">The research desk</p>
            <h2 id="recent-elections" className="mt-3 text-3xl font-bold tracking-tight text-content sm:text-5xl">
              Recently updated
            </h2>
          </div>
          <a href="/elections/" className="hidden text-sm font-semibold text-blue-600 transition hover:text-blue-800 sm:block dark:text-blue-400">
            View the full index →
          </a>
        </header>

        <div className="grid lg:grid-cols-[1.4fr_.8fr]">
          <a href={`/races/${featured.id}/`} className="group border-b border-stroke py-8 lg:border-b-0 lg:border-r lg:pr-10">
            <div className="flex items-center gap-3 text-xs font-semibold uppercase tracking-widest text-content-subtle">
              <span className="rounded-full bg-blue-600 px-3 py-1 text-white">Featured</span>
              <span>Updated {formatDate(featured.updatedUtc)}</span>
            </div>
            <h3 className="mt-8 max-w-2xl text-3xl font-bold leading-tight tracking-tight text-content transition group-hover:text-blue-600 sm:text-5xl dark:group-hover:text-blue-400">
              {featured.title ?? featured.office ?? "Election research"}
            </h3>
            <p className="mt-4 text-lg text-content-muted">{featured.jurisdiction ?? "United States"}</p>
            <div className="mt-10 flex flex-wrap gap-3">
              {featured.candidates.slice(0, 4).map((candidate) => (
                <span key={candidate.name} className="rounded-full border border-stroke px-4 py-2 text-sm font-medium text-content">
                  {candidate.name}
                </span>
              ))}
            </div>
            <p className="mt-10 font-semibold text-blue-600 dark:text-blue-400">
              Open the election guide <span className="inline-block transition group-hover:translate-x-1">→</span>
            </p>
          </a>

          <div className="lg:pl-10">
            {sideRaces.map((race) => (
              <a key={race.id} href={`/races/${race.id}/`} className="group block border-b border-stroke py-6 last:border-0">
                <p className="text-xs font-semibold uppercase tracking-widest text-content-subtle">
                  {race.jurisdiction ?? "National"} · {formatDate(race.updatedUtc)}
                </p>
                <h3 className="mt-2 text-xl font-bold leading-snug text-content transition group-hover:text-blue-600 dark:group-hover:text-blue-400">
                  {race.title ?? race.office}
                </h3>
                <p className="mt-2 text-sm text-content-muted">{race.candidates.length} candidates researched</p>
              </a>
            ))}
          </div>
        </div>

        <a href="/elections/" className="mt-8 inline-block text-sm font-semibold text-blue-600 sm:hidden dark:text-blue-400">
          View the full index →
        </a>
      </div>
    </section>
  );
}
