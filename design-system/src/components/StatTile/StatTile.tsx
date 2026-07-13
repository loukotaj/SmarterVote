import * as React from "react";
import { cx } from "../../utils/cx";

export interface StatTileProps extends React.HTMLAttributes<HTMLDivElement> {
  /** The big number/value (e.g. a countdown digit or a metric total). */
  value: React.ReactNode;
  /** Small caption below the value. */
  label: React.ReactNode;
  /** "tile" = bordered rounded box (ElectionCountdown digits). "bare" = no
   * box, just stacked text (ImpactMetrics stat row). */
  variant?: "tile" | "bare";
  /** "sm" matches ElectionCountdown's compact digit boxes; "lg" matches
   * ImpactMetrics' headline stat numbers. */
  size?: "sm" | "lg";
}

const valueSizeClasses = {
  sm: "text-lg font-black tabular-nums",
  lg: "text-2xl sm:text-3xl font-bold",
};

/**
 * Stat display used by ElectionCountdown's Days/Hrs/Mins/Secs boxes and
 * ImpactMetrics' headline-number row.
 */
export const StatTile = React.forwardRef<HTMLDivElement, StatTileProps>(function StatTile(
  { value, label, variant = "tile", size = "lg", className, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cx(
        "flex flex-col items-center justify-center text-center",
        variant === "tile" && "rounded-xl border border-stroke bg-surface px-4 py-3",
        className,
      )}
      {...rest}
    >
      <span className={cx("text-content leading-none", valueSizeClasses[size])}>{value}</span>
      <span
        className={cx(
          "mt-1 font-medium text-content-subtle",
          size === "sm" ? "text-[9px] font-bold uppercase tracking-wider" : "text-xs sm:text-sm",
        )}
      >
        {label}
      </span>
    </div>
  );
});
