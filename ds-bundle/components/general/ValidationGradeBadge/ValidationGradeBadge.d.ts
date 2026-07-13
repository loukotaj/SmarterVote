import * as React from 'react';

/**
 * ValidationGradeBadge — from @smartervote/design-system@0.1.0.
 */
export interface ValidationGradeBadgeProps {
  grade: ValidationGradeInfo;
  /** Called when the user clicks "View Full Review" inside the popover. */
  onViewReview?: () => void;
}

export declare const ValidationGradeBadge: React.ComponentType<ValidationGradeBadgeProps>;
