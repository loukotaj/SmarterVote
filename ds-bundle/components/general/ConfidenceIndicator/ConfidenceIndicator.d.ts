import * as React from 'react';

/**
 * ConfidenceIndicator — from @smartervote/design-system@0.1.0.
 */
export interface ConfidenceIndicatorProps {
  confidence: "high" | "medium" | "low" | "unknown";
}

export declare const ConfidenceIndicator: React.ComponentType<ConfidenceIndicatorProps>;
