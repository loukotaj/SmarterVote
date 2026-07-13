import * as React from "react";
import { cx } from "../../utils/cx";

export interface TooltipProps {
  /** The element that toggles the popover open when clicked. */
  trigger: React.ReactNode;
  /** Popover panel content. */
  children: React.ReactNode;
  /** Which edge the panel hangs from. Defaults to "left". */
  align?: "left" | "right";
  className?: string;
}

/**
 * Click-to-open popover — the interaction pattern behind
 * ValidationGradeBadge's info panel and IssueTable's renamed-issue
 * tooltips: a backdrop closes it on outside click, Escape closes it too.
 */
export function Tooltip({ trigger, children, align = "left", className }: TooltipProps) {
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <div className="relative inline-flex">
      <button type="button" onClick={() => setOpen((v) => !v)}>
        {trigger}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            role="tooltip"
            className={cx(
              "absolute top-full mt-2 z-50 w-72 bg-surface border border-stroke rounded-lg shadow-lg p-4",
              align === "left" ? "left-0" : "right-0",
              className,
            )}
          >
            {children}
          </div>
        </>
      )}
    </div>
  );
}
