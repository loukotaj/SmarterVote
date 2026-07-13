import * as React from 'react';

/**
 * SiteHeader — from @smartervote/design-system@0.1.0.
 */
export interface SiteHeaderProps {
  links: SiteHeaderLink[];
  darkMode?: boolean;
  onToggleDark?: () => void;
  searchPlaceholder?: string;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  /** Rendered below the search box when non-empty — the results dropdown (Elections/Candidates groups). Left as a slot so the */
  searchResults?: React.ReactNode;
}

export declare const SiteHeader: React.ComponentType<SiteHeaderProps>;
