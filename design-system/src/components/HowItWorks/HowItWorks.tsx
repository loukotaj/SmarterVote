import * as React from "react";

export interface HowItWorksStep {
  title: string;
  description: string;
}

export interface HowItWorksProps {
  eyebrow?: string;
  heading?: React.ReactNode;
  steps?: HowItWorksStep[];
}

const defaultSteps: HowItWorksStep[] = [
  { title: "Find", description: "See the elections that apply to your address." },
  { title: "Compare", description: "Explore structured positions, experience, and donors." },
  { title: "Inspect", description: "Open the original sources and verify each claim." },
];

/**
 * Three-step numbered explainer section, each step with a top border
 * accent and a zero-padded mono step number.
 */
export function HowItWorks({
  eyebrow = "From address to evidence",
  heading = "Three steps. Your conclusions.",
  steps = defaultSteps,
}: HowItWorksProps) {
  return (
    <section className="bg-surface-alt py-20 sm:py-28" aria-labelledby="how-it-works">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="grid gap-12 lg:grid-cols-[.65fr_1.35fr]">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.24em] text-blue-600 dark:text-blue-400">{eyebrow}</p>
            <h2 id="how-it-works" className="mt-4 text-4xl font-bold tracking-tight text-content sm:text-5xl">
              {heading}
            </h2>
          </div>
          <ol className="grid gap-8 sm:grid-cols-3">
            {steps.map((step, index) => (
              <li key={step.title} className="relative border-t-2 border-blue-600 pt-5">
                <span className="font-mono text-xs font-bold text-blue-600 dark:text-blue-400">
                  0{index + 1}
                </span>
                <h3 className="mt-6 text-2xl font-bold text-content">{step.title}</h3>
                <p className="mt-3 leading-7 text-content-muted">{step.description}</p>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
