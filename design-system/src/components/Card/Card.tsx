import * as React from "react";
import { cx } from "../../utils/cx";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** HTML element to render as. Defaults to "div". */
  as?: keyof React.JSX.IntrinsicElements;
}

/**
 * SmarterVote's base surface — a rounded, bordered panel used as the
 * foundation for every card-like composite (CandidateCard, RaceCard, etc).
 */
export const Card = React.forwardRef<HTMLDivElement, CardProps>(function Card(
  { as: Tag = "div", className, children, ...rest },
  ref,
) {
  const Component = Tag as React.ElementType;
  return (
    <Component
      ref={ref}
      className={cx("bg-surface rounded-lg shadow-sm border border-stroke", className)}
      {...rest}
    >
      {children}
    </Component>
  );
});
