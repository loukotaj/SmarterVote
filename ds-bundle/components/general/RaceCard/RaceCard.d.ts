import * as React from 'react';

/**
 * RaceCard — from @smartervote/design-system@0.1.0.
 */
export interface RaceCardProps {
  race: RaceCardData;
  /** Link target. Defaults to "/races/{race.id}". */
  href?: string;
}

export declare const RaceCard: React.ComponentType<RaceCardProps>;
