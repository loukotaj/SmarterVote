import * as React from "react";
import { cx } from "../../utils/cx";

export type BadgeTone = "gray" | "blue" | "green" | "yellow" | "orange" | "red" | "purple" | "teal" | "indigo";
export type BadgeSize = "sm" | "md";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Color family. Mirrors the grade/confidence/office-type color coding used across the app. */
  tone?: BadgeTone;
  /** sm = compact pill (office-type chips), md = default (grades, verdicts). */
  size?: BadgeSize;
}

const toneClasses: Record<BadgeTone, string> = {
  gray: "bg-surface-alt text-content border-stroke",
  blue: "bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 border-blue-300 dark:border-blue-700",
  green: "bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200 border-green-300 dark:border-green-700",
  yellow:
    "bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-200 border-yellow-300 dark:border-yellow-700",
  orange:
    "bg-orange-100 dark:bg-orange-900/40 text-orange-800 dark:text-orange-200 border-orange-300 dark:border-orange-700",
  red: "bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-200 border-red-300 dark:border-red-700",
  purple:
    "bg-purple-100 dark:bg-purple-900/40 text-purple-800 dark:text-purple-200 border-purple-300 dark:border-purple-700",
  teal: "bg-teal-100 dark:bg-teal-900/40 text-teal-800 dark:text-teal-200 border-teal-300 dark:border-teal-700",
  indigo:
    "bg-indigo-100 dark:bg-indigo-900/40 text-indigo-800 dark:text-indigo-200 border-indigo-300 dark:border-indigo-700",
};

const sizeClasses: Record<BadgeSize, string> = {
  sm: "px-2 py-0.5 text-xs",
  md: "px-3 py-1 text-sm",
};

/**
 * Generic colored pill — generalizes the grade (A–F), confidence
 * (high/medium/low), office-type, and review-verdict color coding
 * repeated across ValidationGradeBadge, RaceCard, and ReviewPanel.
 */
export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(function Badge(
  { tone = "gray", size = "md", className, children, ...rest },
  ref,
) {
  return (
    <span
      ref={ref}
      className={cx(
        "inline-flex items-center gap-1 rounded-full border font-semibold",
        toneClasses[tone],
        sizeClasses[size],
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
});
