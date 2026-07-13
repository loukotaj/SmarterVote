import * as React from 'react';

/**
 * StatTile — from @smartervote/design-system@0.1.0.
 */
export interface StatTileProps {
  /** The big number/value (e.g. a countdown digit or a metric total). */
  value: React.ReactNode;
  /** Small caption below the value. */
  label: React.ReactNode;
  /** "tile" = bordered rounded box (ElectionCountdown digits). "bare" = no box, just stacked text (ImpactMetrics stat row). */
  variant?: "tile" | "bare";
  /** "sm" matches ElectionCountdown's compact digit boxes; "lg" matches ImpactMetrics' headline stat numbers. */
  size?: "sm" | "lg";
  className?: string;
  id?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}

export declare const StatTile: React.ComponentType<StatTileProps>;
