import * as React from 'react';

/**
 * EmptyState — from @smartervote/design-system@0.1.0.
 */
export interface EmptyStateProps {
  /** Main message explaining what's missing. */
  message: React.ReactNode;
  /** Optional smaller supporting text below the action. */
  helpText?: React.ReactNode;
  /** Optional CTA link (e.g. "Help improve this data"). */
  action?: EmptyStateAction;
}

export declare const EmptyState: React.ComponentType<EmptyStateProps>;
