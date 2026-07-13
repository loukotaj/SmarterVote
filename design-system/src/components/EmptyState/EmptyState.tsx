import * as React from "react";

export interface EmptyStateAction {
  label: React.ReactNode;
  href: string;
}

export interface EmptyStateProps {
  /** Main message explaining what's missing. */
  message: React.ReactNode;
  /** Optional smaller supporting text below the action. */
  helpText?: React.ReactNode;
  /** Optional CTA link (e.g. "Help improve this data"). */
  action?: EmptyStateAction;
}

/**
 * Friendly "no data yet" block — generalized from NoDataFallback, which
 * SmarterVote uses when a candidate is missing issues/donor/voting data.
 */
export function EmptyState({ message, helpText, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-8 px-4 text-center bg-surface-alt rounded-lg border border-stroke">
      <div className="mb-4">
        <svg className="w-12 h-12 text-content-faint" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z"
          />
        </svg>
      </div>

      <p className="text-content-muted text-sm sm:text-base mb-4 max-w-md">{message}</p>

      {action && (
        <a
          href={action.href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors duration-200 text-sm sm:text-base"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244"
            />
          </svg>
          {action.label}
        </a>
      )}

      {helpText && <p className="text-content-subtle text-xs sm:text-sm mt-3 max-w-sm">{helpText}</p>}
    </div>
  );
}
