Button from @smartervote/design-system. Use via `window.SmarterVoteDS.Button` (bundle loaded from the root `_ds_bundle.js`).

SmarterVote's button — synthesized from the repeated Tailwind class
strings used across the Svelte app (no dedicated Button.svelte exists
there). Five variants cover every de-facto style found: primary CTA,
secondary/neutral, outline, pill/segmented-toggle (filters, tabs), danger.

## Props

```ts
interface ButtonProps {
  /** Visual style. "pill" is the rounded-full segmented/filter-chip toggle style. */
  variant?: "primary" | "secondary" | "outline" | "pill" | "danger";
  /** Size affects padding and border radius (pill stays rounded-full at every size). */
  size?: "sm" | "md" | "lg";
  /** Only meaningful for variant="pill" — marks the chip as the selected/active toggle. */
  active?: boolean;
  className?: string;
  id?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}
```
