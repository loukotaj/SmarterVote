import * as React from "react";
import { cx } from "../../utils/cx";

export type ButtonVariant = "primary" | "secondary" | "outline" | "pill" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual style. "pill" is the rounded-full segmented/filter-chip toggle style. */
  variant?: ButtonVariant;
  /** Size affects padding and border radius (pill stays rounded-full at every size). */
  size?: ButtonSize;
  /** Only meaningful for variant="pill" — marks the chip as the selected/active toggle. */
  active?: boolean;
}

const base =
  "inline-flex items-center justify-center gap-1.5 font-medium transition-colors " +
  "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 " +
  "disabled:opacity-60 disabled:cursor-not-allowed";

const variantClasses: Record<Exclude<ButtonVariant, "pill">, string> = {
  primary: "bg-blue-600 hover:bg-blue-700 text-white rounded-lg",
  secondary: "bg-surface-alt text-content hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg",
  outline:
    "rounded-xl border border-blue-200 bg-blue-50 text-blue-800 hover:bg-blue-100 " +
    "dark:border-blue-800 dark:bg-blue-950 dark:text-blue-200",
  danger: "bg-red-600 hover:bg-red-700 text-white rounded-lg",
};

const pillClasses = {
  active: "rounded-full border bg-blue-600 text-white border-blue-600 shadow-md shadow-blue-600/20",
  inactive:
    "rounded-full border border-stroke bg-surface text-content-muted hover:border-blue-400 hover:text-blue-700",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
};

/**
 * SmarterVote's button — synthesized from the repeated Tailwind class
 * strings used across the Svelte app (no dedicated Button.svelte exists
 * there). Five variants cover every de-facto style found: primary CTA,
 * secondary/neutral, outline, pill/segmented-toggle (filters, tabs), danger.
 */
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", active = false, className, children, ...rest },
  ref,
) {
  const variantClass = variant === "pill" ? pillClasses[active ? "active" : "inactive"] : variantClasses[variant];

  return (
    <button ref={ref} className={cx(base, variantClass, sizeClasses[size], className)} {...rest}>
      {children}
    </button>
  );
});
