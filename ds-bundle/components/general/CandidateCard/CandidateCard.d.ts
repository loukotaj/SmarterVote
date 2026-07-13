import * as React from 'react';

/**
 * CandidateCard — from @smartervote/design-system@0.1.0.
 */
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

export declare const CandidateCard: React.ComponentType<CandidateCardProps>;
