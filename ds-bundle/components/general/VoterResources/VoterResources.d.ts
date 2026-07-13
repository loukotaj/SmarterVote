import * as React from 'react';

/**
 * VoterResources — from @smartervote/design-system@0.1.0.
 */
export interface VoterResourcesProps {
  ballotpediaUrl?: string;
  registerToVoteUrl?: string;
  howToVoteUrl?: string;
  hasForecast?: boolean;
  onJumpToForecast?: () => void;
}

export declare const VoterResources: React.ComponentType<VoterResourcesProps>;
