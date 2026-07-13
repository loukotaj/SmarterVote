import * as React from 'react';

/**
 * SiteFooter — from @smartervote/design-system@0.1.0.
 */
export interface SiteFooterProps {
  links: SiteFooterLink[];
  /** AI-disclosure notice text. Defaults to SmarterVote's standard notice. */
  aiNotice?: React.ReactNode;
}

export declare const SiteFooter: React.ComponentType<SiteFooterProps>;
