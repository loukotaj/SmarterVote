import * as React from "react";

export interface SiteFooterLink {
  href: string;
  label: string;
  external?: boolean;
}

export interface SiteFooterProps {
  links: SiteFooterLink[];
  /** AI-disclosure notice text. Defaults to SmarterVote's standard notice. */
  aiNotice?: React.ReactNode;
}

const defaultNotice = (
  <>
    <strong>AI-generated content notice:</strong> Candidate summaries, comparisons, classifications, and forecasts may
    be generated with AI and can be incomplete, incorrect, or outdated. Check the linked evidence and official
    election sources before relying on them.{" "}
    <a href="/about/#ai-generated-content" className="ml-1 font-semibold underline underline-offset-2 hover:no-underline">
      How Smarter.Vote uses AI
    </a>
    .
  </>
);

/**
 * Site footer — wordmark + tagline, nav links, an amber AI-disclosure
 * notice box, and a copyright line.
 */
export function SiteFooter({ links, aiNotice = defaultNotice }: SiteFooterProps) {
  return (
    <footer className="mt-12 border-t border-stroke bg-surface sm:mt-16">
      <div className="container mx-auto max-w-7xl px-4 py-8">
        <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
          <div className="max-w-xl">
            <a href="/" className="font-bold text-blue-600">
              Smarter.Vote
            </a>
            <p className="mt-2 text-sm text-content-muted">
              Independent, sourced election research for informational purposes. Always confirm voting information
              with official election authorities.
            </p>
          </div>
          <nav className="flex max-w-xl flex-wrap gap-x-5 gap-y-3 text-sm" aria-label="Footer navigation">
            {links.map((link) => (
              <a
                key={link.href}
                href={link.href}
                target={link.external ? "_blank" : undefined}
                rel={link.external ? "noopener noreferrer" : undefined}
                className="text-content-muted hover:text-content"
              >
                {link.label}
              </a>
            ))}
          </nav>
        </div>

        <div
          role="note"
          aria-label="AI-generated content notice"
          className="mt-7 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
        >
          {aiNotice}
        </div>

        <p className="mt-8 border-t border-stroke pt-5 text-xs text-content-subtle">
          © {new Date().getFullYear()} Smarter.Vote LLC. Not affiliated with any government or political campaign.
        </p>
      </div>
    </footer>
  );
}
