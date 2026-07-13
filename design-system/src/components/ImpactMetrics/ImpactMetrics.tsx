export interface ImpactMetricsData {
  guides: number;
  candidateProfiles: number;
  statesRepresented: number;
  lastUpdated: string;
  snapshotDate: string;
}

export interface ImpactMetricsProps {
  metrics: ImpactMetricsData;
}

function formatDate(date: string): string {
  return new Date(date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/**
 * Coverage-stats strip (guides published, candidate profiles, states
 * represented, last-updated date) shown on the homepage.
 */
export function ImpactMetrics({ metrics }: ImpactMetricsProps) {
  return (
    <section className="border-y border-stroke bg-surface-alt py-12" aria-labelledby="coverage-metrics">
      <div className="mx-auto max-w-6xl px-4">
        <h2 id="coverage-metrics" className="sr-only">
          Current published coverage
        </h2>
        <dl className="grid gap-7 text-center sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-sm text-content-muted">Published election guides</dt>
            <dd className="mt-1 text-3xl font-bold text-content">{metrics.guides.toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-sm text-content-muted">Candidate profiles</dt>
            <dd className="mt-1 text-3xl font-bold text-content">{metrics.candidateProfiles.toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-sm text-content-muted">States represented</dt>
            <dd className="mt-1 text-3xl font-bold text-content">{metrics.statesRepresented}</dd>
          </div>
          <div>
            <dt className="text-sm text-content-muted">Research last updated</dt>
            <dd className="mt-1 text-xl font-bold text-content">{formatDate(metrics.lastUpdated)}</dd>
          </div>
        </dl>
        <p className="mt-7 text-center text-xs text-content-subtle">
          Published-data snapshot: {formatDate(metrics.snapshotDate)}. Counts describe Smarter.Vote coverage, not every
          contest on a ballot.
        </p>
      </div>
    </section>
  );
}
