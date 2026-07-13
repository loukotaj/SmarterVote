import * as React from 'react';

/**
 * Avatar — from @smartervote/design-system@0.1.0.
 */
export interface AvatarProps {
  /** Full name — used to derive initials when no image is provided. */
  name: string;
  /** Optional photo URL. Falls back to initials-on-blue when omitted or broken. */
  src?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
  id?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}

export declare const Avatar: React.ComponentType<AvatarProps>;
