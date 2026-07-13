import * as React from "react";
import { cx } from "../../utils/cx";

export type AvatarSize = "sm" | "md" | "lg";

export interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Full name — used to derive initials when no image is provided. */
  name: string;
  /** Optional photo URL. Falls back to initials-on-blue when omitted or broken. */
  src?: string;
  size?: AvatarSize;
}

const sizeClasses: Record<AvatarSize, string> = {
  sm: "w-8 h-8 text-xs",
  md: "w-12 h-12 text-sm",
  lg: "w-16 h-16 text-lg",
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase();
}

/**
 * Circular candidate/user avatar — photo when available, otherwise
 * initials on a blue tint (the fallback used throughout CandidateCard
 * and RaceCard). Wrap in an element with a `ring-*` class for the
 * party-colored ring RaceCard applies around each candidate thumbnail.
 */
export const Avatar = React.forwardRef<HTMLDivElement, AvatarProps>(function Avatar(
  { name, src, size = "md", className, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cx(
        "inline-flex items-center justify-center rounded-full overflow-hidden shrink-0",
        "bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 font-semibold",
        sizeClasses[size],
        className,
      )}
      {...rest}
    >
      {src ? (
        <img src={src} alt={name} className="w-full h-full object-cover" />
      ) : (
        <span>{initials(name)}</span>
      )}
    </div>
  );
});
