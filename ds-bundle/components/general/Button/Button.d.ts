import * as React from 'react';

/**
 * Button — from @smartervote/design-system@0.1.0.
 * @replaces button
 */
export interface ButtonProps {
  /** Visual style. "pill" is the rounded-full segmented/filter-chip toggle style. */
  variant?: "primary" | "secondary" | "outline" | "pill" | "danger";
  /** Size affects padding and border radius (pill stays rounded-full at every size). */
  size?: "sm" | "md" | "lg";
  /** Only meaningful for variant="pill" — marks the chip as the selected/active toggle. */
  active?: boolean;
  className?: string;
  id?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}

export declare const Button: React.ComponentType<ButtonProps>;
