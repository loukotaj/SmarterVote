import * as React from 'react';

/**
 * SourceLink — from @smartervote/design-system@0.1.0.
 */
export interface SourceLinkProps {
  /** Source URL. Only http/https URLs render as a link — anything else falls back to plain text. */
  url: string;
  /** Optional source title, used for the label and title-attribute fallback. */
  title?: string;
  /** Explicit label override. Falls back to title, then the URL's domain. */
  text?: string;
}

export declare const SourceLink: React.ComponentType<SourceLinkProps>;
