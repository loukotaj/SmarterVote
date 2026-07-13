import * as React from "react";

export interface SectionHeaderProps {
  /** Small uppercase label above the title (e.g. "Smarter.Vote"). */
  eyebrow?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
}

/**
 * Eyebrow / title / description page-header pattern, used at the top of
 * every support/policy page (TrustPage) and section intros.
 */
export function SectionHeader({ eyebrow, title, description }: SectionHeaderProps) {
  return (
    <header className="max-w-3xl">
      {eyebrow && (
        <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-500">
          {eyebrow}
        </p>
      )}
      <h1 className="text-3xl font-bold tracking-tight text-content sm:text-4xl">{title}</h1>
      {description && <p className="mt-4 text-lg leading-8 text-content-muted">{description}</p>}
    </header>
  );
}
