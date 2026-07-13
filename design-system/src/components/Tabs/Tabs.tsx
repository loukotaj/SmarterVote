import * as React from "react";
import { cx } from "../../utils/cx";

export interface TabItem {
  value: string;
  label: React.ReactNode;
  disabled?: boolean;
}

export interface TabsProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "onChange"> {
  items: TabItem[];
  /** Currently selected tab value (controlled). */
  value: string;
  onChange: (value: string) => void;
}

/**
 * Underline tab bar — the CandidateCard body switcher (Issues / Background
 * / Donors / Voting). Controlled: the parent owns `value` and swaps the
 * panel content itself; Tabs only renders the row of buttons.
 */
export const Tabs = React.forwardRef<HTMLDivElement, TabsProps>(function Tabs(
  { items, value, onChange, className, ...rest },
  ref,
) {
  return (
    <div ref={ref} role="tablist" className={cx("flex gap-1 border-b border-stroke", className)} {...rest}>
      {items.map((item) => {
        const active = item.value === value;
        return (
          <button
            key={item.value}
            role="tab"
            type="button"
            aria-selected={active}
            disabled={item.disabled}
            onClick={() => onChange(item.value)}
            className={cx(
              "px-3 py-2 text-sm font-medium border-b-2 transition-colors duration-200",
              item.disabled
                ? "border-transparent text-content-faint cursor-not-allowed"
                : active
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-content-subtle hover:text-content-muted hover:border-stroke",
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
});
