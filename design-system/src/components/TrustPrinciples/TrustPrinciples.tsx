import * as React from "react";

export interface TrustPrinciple {
  number: string;
  title: string;
  description: string;
}

export interface TrustPrinciplesProps {
  eyebrow?: string;
  heading?: React.ReactNode;
  description?: string;
  ctaHref?: string;
  ctaLabel?: string;
  principles?: TrustPrinciple[];
}

const defaultPrinciples: TrustPrinciple[] = [
  {
    number: "01",
    title: "Every claim links to a source",
    description: "Follow the research back to candidate statements, public records, and reputable reporting.",
  },
  {
    number: "02",
    title: "Uncertainty stays visible",
    description:
      "Sparse evidence, conflicting accounts, and confidence levels are part of the record—not hidden in fine print.",
  },
  {
    number: "03",
    title: "No endorsements. Ever.",
    description: "We organize evidence consistently across parties. The judgment about what matters remains yours.",
  },
];

/**
 * Always-dark editorial section (bg-blue-950, white text) even when the
 * rest of the page is in light mode — SmarterVote's "editorial promise"
 * block on the homepage.
 */
export function TrustPrinciples({
  eyebrow = "Our editorial promise",
  heading = "Don't take our word for it.",
  description = "Read the evidence, see where it disagrees, and decide for yourself.",
  ctaHref = "/about/#methodology",
  ctaLabel = "Examine our methodology →",
  principles = defaultPrinciples,
}: TrustPrinciplesProps) {
  return (
    <section className="bg-blue-950 py-20 text-white sm:py-28" aria-labelledby="trust-heading">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="grid gap-12 lg:grid-cols-[.72fr_1.28fr] lg:gap-20">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.24em] text-blue-300">{eyebrow}</p>
            <h2 id="trust-heading" className="mt-4 text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
              {heading}
            </h2>
            <p className="mt-5 max-w-md text-lg leading-8 text-blue-100/75">{description}</p>
            <a href={ctaHref} className="mt-8 inline-flex border-b border-blue-400 pb-1 font-semibold text-blue-200 transition hover:text-white">
              {ctaLabel}
            </a>
          </div>
          <div className="divide-y divide-blue-800 border-y border-blue-800">
            {principles.map((principle) => (
              <article key={principle.number} className="grid grid-cols-[3rem_1fr] gap-4 py-7 sm:grid-cols-[4rem_1fr]">
                <span className="font-mono text-sm text-blue-400">{principle.number}</span>
                <div>
                  <h3 className="text-xl font-bold sm:text-2xl">{principle.title}</h3>
                  <p className="mt-2 max-w-xl leading-7 text-blue-100/70">{principle.description}</p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
