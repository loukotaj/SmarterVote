import * as React from "react";
import { Card } from "../Card";
import { Avatar } from "../Avatar";
import { Tabs, type TabItem } from "../Tabs";
import { ConfidenceIndicator, type ConfidenceLevel } from "../ConfidenceIndicator";
import { SourceLink } from "../SourceLink";
import { partyAbbr } from "../../utils/party";

export interface CandidateCardIssue {
  issue: string;
  stance: string;
  confidence: ConfidenceLevel;
}

export interface CareerEntry {
  title: string;
  organization?: string;
  startYear?: number;
  endYear?: number;
  description?: string;
  sourceUrl?: string;
  sourceTitle?: string;
}

export interface EducationEntry {
  institution: string;
  degree?: string;
  field?: string;
  year?: number;
  sourceUrl?: string;
  sourceTitle?: string;
}

export interface CandidateCardData {
  name: string;
  party?: string;
  incumbent?: boolean;
  imageUrl?: string;
  summary?: string;
  websiteUrl?: string;
  issues?: CandidateCardIssue[];
  careerHistory?: CareerEntry[];
  education?: EducationEntry[];
  donorSummary?: string;
  donorSources?: { url: string; title?: string }[];
  votingSummary?: string;
  votingSources?: { url: string; title?: string }[];
}

export interface CandidateCardProps {
  candidate: CandidateCardData;
  /** Link target for the candidate's name — omit to render as plain text. */
  href?: string;
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: () => void;
  /** Whether the tabbed detail section starts open. Defaults to false. */
  defaultExpanded?: boolean;
}

const externalIcon = (
  <svg className="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
    />
  </svg>
);

/**
 * The candidate profile card — the app's most visually dense composite.
 * Header (avatar, name, party/incumbent badges, summary) is always
 * visible; "Show More" reveals a tabbed detail section (Key Issues,
 * Background, Donors, Voting Record).
 */
export function CandidateCard({ candidate, href, selectable = false, selected = false, onToggleSelect, defaultExpanded = false }: CandidateCardProps) {
  const [expanded, setExpanded] = React.useState(defaultExpanded);
  const [activeTab, setActiveTab] = React.useState<"issues" | "background" | "donors" | "voting">("issues");

  const hasCareer = !!candidate.careerHistory?.length;
  const hasEducation = !!candidate.education?.length;
  const hasBackground = hasCareer || hasEducation;
  const hasVoting = !!candidate.votingSummary;
  const hasDonors = !!candidate.donorSummary;

  const summary = candidate.summary ?? "";
  const summaryPreview = summary.length > 600 ? `${summary.slice(0, 600)}...` : summary;

  const tabItems: TabItem[] = [
    { value: "issues", label: "Key Issues" },
    { value: "background", label: "Background", disabled: !hasBackground },
    { value: "donors", label: "Donors", disabled: !hasDonors },
    { value: "voting", label: "Voting Record", disabled: !hasVoting },
  ];

  const nameNode = (
    <>
      {candidate.name}
      {href && (
        <svg className="inline w-4 h-4 ml-1 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
          />
        </svg>
      )}
    </>
  );

  return (
    <Card className="p-3 sm:p-4 lg:p-6 h-full w-full mx-auto shadow-lg">
      <div className="mb-6">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-start gap-4">
            {selectable && (
              <div className="flex items-center shrink-0 self-center">
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={onToggleSelect}
                  aria-label={`Select ${candidate.name} to compare`}
                  className="w-5 h-5 cursor-pointer text-blue-600 border-stroke rounded focus:ring-blue-500 bg-surface"
                />
              </div>
            )}

            <Avatar name={candidate.name} src={candidate.imageUrl} size="lg" className="border-2 border-stroke" />

            <div>
              <h3 className="text-lg sm:text-xl lg:text-2xl font-bold text-content flex items-center gap-2">
                {href ? (
                  <a href={href} className="text-blue-600 hover:text-blue-500 dark:hover:text-blue-400 hover:underline transition-colors duration-200 no-underline">
                    {nameNode}
                  </a>
                ) : (
                  nameNode
                )}
              </h3>
              <div className="flex flex-wrap items-center gap-1 mt-1">
                {candidate.party && (
                  <span
                    title={candidate.party}
                    className="px-2 sm:px-3 py-1 rounded-full text-xs sm:text-sm font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                  >
                    {partyAbbr(candidate.party)}
                  </span>
                )}
                {candidate.incumbent && (
                  <span className="px-2 sm:px-3 py-1 rounded-full text-xs sm:text-sm font-medium bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200">
                    Incumbent
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        <p className="text-content-muted leading-relaxed text-xs sm:text-sm lg:text-base">{expanded ? summary : summaryPreview}</p>

        {candidate.websiteUrl && (
          <div className="mt-3">
            <a
              href={candidate.websiteUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 font-medium hover:text-blue-500 dark:hover:text-blue-300"
            >
              Official Website
              {externalIcon}
            </a>
          </div>
        )}

        <div className="mt-4">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse candidate details" : "Expand candidate details"}
            className="flex items-center gap-2 text-blue-600 dark:text-blue-400 font-medium transition-colors duration-200 hover:text-blue-500 dark:hover:text-blue-300"
          >
            <span className="text-xs sm:text-sm font-medium">{expanded ? "Show Less" : "Show More"}</span>
            <svg
              className={`w-4 h-4 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-stroke pt-4 sm:pt-6">
          <Tabs items={tabItems} value={activeTab} onChange={(v) => setActiveTab(v as typeof activeTab)} className="mb-6 overflow-x-auto" />

          <div className="min-h-32">
            {activeTab === "issues" &&
              (candidate.issues?.length ? (
                <div className="space-y-3">
                  {candidate.issues.map((issue) => (
                    <div key={issue.issue} className="flex flex-wrap items-center justify-between gap-2 border-b border-stroke pb-3 last:border-0">
                      <div>
                        <p className="text-sm font-medium text-content">{issue.issue}</p>
                        <p className="text-sm text-content-muted">{issue.stance}</p>
                      </div>
                      <ConfidenceIndicator confidence={issue.confidence} />
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-content-subtle text-sm">No issue stances available yet.</p>
              ))}

            {activeTab === "background" && (
              <div className="space-y-4">
                {hasCareer && (
                  <div className="mb-6">
                    <h4 className="text-base sm:text-lg font-semibold text-content mb-3 sm:mb-4">Career History</h4>
                    <div className="space-y-3">
                      {candidate.careerHistory!.map((entry) => (
                        <div key={entry.title} className="border-l-2 border-blue-200 dark:border-blue-700 pl-4 py-1">
                          <div className="flex flex-wrap items-baseline gap-2">
                            <span className="font-medium text-content text-sm">{entry.title}</span>
                            {entry.startYear && (
                              <span className="text-xs text-content-subtle">
                                {entry.startYear}
                                {entry.endYear ? ` – ${entry.endYear}` : " – Present"}
                              </span>
                            )}
                          </div>
                          {entry.organization && <span className="text-sm text-content-muted block">{entry.organization}</span>}
                          {entry.description && <p className="text-xs text-content-subtle mt-1">{entry.description}</p>}
                          {entry.sourceUrl && (
                            <SourceLink url={entry.sourceUrl} title={entry.sourceTitle ?? "Source"} />
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {hasEducation && (
                  <div>
                    <h4 className="text-base sm:text-lg font-semibold text-content mb-3 sm:mb-4">Education</h4>
                    <div className="space-y-2">
                      {candidate.education!.map((edu) => (
                        <div key={edu.institution} className="flex flex-col">
                          <span className="font-medium text-content text-sm">{edu.institution}</span>
                          {(edu.degree || edu.field) && (
                            <span className="text-xs text-content-muted">
                              {[edu.degree, edu.field].filter(Boolean).join(" in ")}
                              {edu.year ? ` (${edu.year})` : ""}
                            </span>
                          )}
                          {edu.sourceUrl && <SourceLink url={edu.sourceUrl} title={edu.sourceTitle ?? "Source"} />}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {!hasBackground && <p className="text-content-subtle text-sm">No background information available yet.</p>}
              </div>
            )}

            {activeTab === "donors" && (
              <div className="bg-surface-alt rounded-lg p-4">
                <p className="text-sm text-content-muted mb-3">{candidate.donorSummary || "No donor information available yet."}</p>
                <div className="flex flex-wrap gap-2">
                  {candidate.donorSources?.map((source) => (
                    <span key={source.url} className="rounded-lg bg-primary-500/10 border border-primary-500/30 px-3 py-1.5">
                      <SourceLink url={source.url} title={source.title} />
                    </span>
                  ))}
                </div>
              </div>
            )}

            {activeTab === "voting" && (
              <div className="bg-surface-alt rounded-lg p-4">
                <p className="text-sm text-content-muted mb-3">{candidate.votingSummary || "No voting record available yet."}</p>
                <div className="flex flex-wrap gap-2">
                  {candidate.votingSources?.map((source) => (
                    <span key={source.url} className="rounded-lg bg-primary-500/10 border border-primary-500/30 px-3 py-1.5">
                      <SourceLink url={source.url} title={source.title} />
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
