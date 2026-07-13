import * as React from 'react';

/**
 * SectionHeader — from @smartervote/design-system@0.1.0.
 */
export interface SectionHeaderProps {
  /** Small uppercase label above the title (e.g. "Smarter.Vote"). */
  eyebrow?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
}

export declare const SectionHeader: React.ComponentType<SectionHeaderProps>;
