import * as React from 'react';

/**
 * Tooltip — from @smartervote/design-system@0.1.0.
 */
export interface TooltipProps {
  /** The element that toggles the popover open when clicked. */
  trigger: React.ReactNode;
  /** Popover panel content. */
  children: React.ReactNode;
  /** Which edge the panel hangs from. Defaults to "left". */
  align?: "left" | "right";
  className?: string;
}

export declare const Tooltip: React.ComponentType<TooltipProps>;
