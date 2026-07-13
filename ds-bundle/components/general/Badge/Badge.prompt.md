Badge from @smartervote/design-system. Use via `window.SmarterVoteDS.Badge` (bundle loaded from the root `_ds_bundle.js`).

Generic colored pill — generalizes the grade (A–F), confidence
(high/medium/low), office-type, and review-verdict color coding
repeated across ValidationGradeBadge, RaceCard, and ReviewPanel.

## Props

```ts
interface BadgeProps {
  /** Color family. Mirrors the grade/confidence/office-type color coding used across the app. */
  tone?: "gray" | "blue" | "green" | "yellow" | "orange" | "red" | "purple" | "teal" | "indigo";
  /** sm = compact pill (office-type chips), md = default (grades, verdicts). */
  size?: "sm" | "md";
  className?: string;
  id?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}
```
