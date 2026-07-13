import * as React from 'react';

/**
 * Badge — from @smartervote/design-system@0.1.0.
 */
export interface BadgeProps {
  /** Color family. Mirrors the grade/confidence/office-type color coding used across the app. */
  tone?: "gray" | "blue" | "green" | "yellow" | "orange" | "red" | "purple" | "teal" | "indigo";
  /** sm = compact pill (office-type chips), md = default (grades, verdicts). */
  size?: "sm" | "md";
  className?: string;
  id?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}

export declare const Badge: React.ComponentType<BadgeProps>;
