import * as React from 'react';

/**
 * FeaturedElections — from @smartervote/design-system@0.1.0.
 */
export interface FeaturedElectionsProps {
  /** First race is the large "Featured" story; up to 4 more render as the side list. */
  races: FeaturedElectionsRace[];
}

export declare const FeaturedElections: React.ComponentType<FeaturedElectionsProps>;
