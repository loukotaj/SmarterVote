import * as React from 'react';

/**
 * TrustPrinciples — from @smartervote/design-system@0.1.0.
 */
export interface TrustPrinciplesProps {
  eyebrow?: string;
  heading?: React.ReactNode;
  description?: string;
  ctaHref?: string;
  ctaLabel?: string;
  principles?: TrustPrinciple[];
}

export declare const TrustPrinciples: React.ComponentType<TrustPrinciplesProps>;
