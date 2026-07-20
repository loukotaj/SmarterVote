import * as React from "react";
import { Badge, type BadgeTone } from "../components/Badge";
import { Card } from "../components/Card";
import { StatTile } from "../components/StatTile";
import { cx } from "../utils/cx";

export type MarketingFormat = "square" | "landscape" | "story" | "document";

const formatClasses: Record<MarketingFormat, string> = {
  square: "aspect-square max-w-[1080px]",
  landscape: "aspect-[16/9] max-w-[1200px]",
  story: "aspect-[9/16] max-w-[675px]",
  document: "aspect-[8.5/11] max-w-[850px]",
};

export interface MarketingFrameProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  format?: MarketingFormat;
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  footer?: React.ReactNode;
}

/** Branded canvas with export-friendly aspect ratios for Claude-generated assets. */
export function MarketingFrame({
  format = "square",
  eyebrow = "SmarterVote",
  title,
  subtitle,
  footer = "Research the race. Compare the candidates. Vote informed.",
  children,
  className,
  ...rest
}: MarketingFrameProps) {
  return (
    <section
      className={cx(
        "flex w-full flex-col overflow-hidden bg-page p-10 text-content sm:p-14",
        formatClasses[format],
        className,
      )}
      {...rest}
    >
      <header>
        <p className="text-sm font-black uppercase tracking-[0.2em] text-primary">{eyebrow}</p>
        <h1 className="mt-4 max-w-4xl text-4xl font-black leading-tight sm:text-6xl">{title}</h1>
        {subtitle && <p className="mt-4 max-w-3xl text-lg leading-relaxed text-content-muted sm:text-2xl">{subtitle}</p>}
      </header>
      <div className="my-8 flex-1">{children}</div>
      <footer className="border-t border-stroke pt-5 text-sm font-semibold text-content-subtle">{footer}</footer>
    </section>
  );
}

export interface SocialAnnouncementProps extends Omit<MarketingFrameProps, "children"> {
  callout: string;
  calloutTone?: BadgeTone;
  highlights?: string[];
}

export function SocialAnnouncement({
  callout,
  calloutTone = "blue",
  highlights = [],
  ...frameProps
}: SocialAnnouncementProps) {
  return (
    <MarketingFrame {...frameProps}>
      <div className="flex h-full flex-col justify-end gap-6">
        <Badge tone={calloutTone} size="md" className="w-fit text-base">
          {callout}
        </Badge>
        {highlights.length > 0 && (
          <ul className="grid gap-3 text-lg font-semibold sm:grid-cols-2">
            {highlights.map((highlight) => (
              <li key={highlight} className="rounded-lg border border-stroke bg-surface p-4">
                {highlight}
              </li>
            ))}
          </ul>
        )}
      </div>
    </MarketingFrame>
  );
}

export interface ComparisonCandidate {
  name: string;
  party?: string;
  summary: string;
}

export interface CandidateComparisonGraphicProps extends Omit<MarketingFrameProps, "children"> {
  candidates: ComparisonCandidate[];
  issue: string;
  sourceNote?: string;
}

export function CandidateComparisonGraphic({
  candidates,
  issue,
  sourceNote = "Summaries are sourced and reviewed. Visit SmarterVote for citations.",
  ...frameProps
}: CandidateComparisonGraphicProps) {
  return (
    <MarketingFrame {...frameProps} footer={sourceNote}>
      <p className="mb-5 text-sm font-black uppercase tracking-wider text-content-subtle">Issue: {issue}</p>
      <div className="grid gap-5 sm:grid-cols-2">
        {candidates.slice(0, 4).map((candidate) => (
          <Card key={candidate.name} className="p-6">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-2xl font-black">{candidate.name}</h2>
              {candidate.party && <Badge size="sm">{candidate.party}</Badge>}
            </div>
            <p className="mt-4 leading-relaxed text-content-muted">{candidate.summary}</p>
          </Card>
        ))}
      </div>
    </MarketingFrame>
  );
}

export interface CampaignMetric {
  value: React.ReactNode;
  label: React.ReactNode;
}

export interface CampaignUpdateProps extends Omit<MarketingFrameProps, "children"> {
  metrics: CampaignMetric[];
  update: React.ReactNode;
}

export function CampaignUpdate({ metrics, update, ...frameProps }: CampaignUpdateProps) {
  return (
    <MarketingFrame {...frameProps}>
      <div className="flex h-full flex-col justify-between gap-8">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {metrics.slice(0, 6).map((metric, index) => (
            <StatTile key={index} value={metric.value} label={metric.label} />
          ))}
        </div>
        <Card className="border-primary/30 bg-blue-50 p-6 text-lg leading-relaxed dark:bg-blue-950/30">{update}</Card>
      </div>
    </MarketingFrame>
  );
}

export interface ResearchReportCoverProps extends Omit<MarketingFrameProps, "children"> {
  electionDate?: string;
  preparedFor?: string;
  topics?: string[];
}

export function ResearchReportCover({ electionDate, preparedFor, topics = [], ...frameProps }: ResearchReportCoverProps) {
  return (
    <MarketingFrame format="document" {...frameProps}>
      <div className="flex h-full flex-col justify-end gap-7">
        <div className="h-2 w-24 rounded-full bg-primary" />
        {topics.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {topics.map((topic) => (
              <Badge key={topic} tone="blue">
                {topic}
              </Badge>
            ))}
          </div>
        )}
        <dl className="grid gap-4 border-t border-stroke pt-6 text-content-muted sm:grid-cols-2">
          {electionDate && (
            <div>
              <dt className="text-xs font-black uppercase tracking-wider">Election date</dt>
              <dd className="mt-1 text-lg font-semibold text-content">{electionDate}</dd>
            </div>
          )}
          {preparedFor && (
            <div>
              <dt className="text-xs font-black uppercase tracking-wider">Prepared for</dt>
              <dd className="mt-1 text-lg font-semibold text-content">{preparedFor}</dd>
            </div>
          )}
        </dl>
      </div>
    </MarketingFrame>
  );
}
