import * as React from 'react';

/**
 * HowItWorks — from @smartervote/design-system@0.1.0.
 */
export interface HowItWorksProps {
  eyebrow?: string;
  heading?: React.ReactNode;
  steps?: HowItWorksStep[];
}

export declare const HowItWorks: React.ComponentType<HowItWorksProps>;
