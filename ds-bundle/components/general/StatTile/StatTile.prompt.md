StatTile from @smartervote/design-system. Use via `window.SmarterVoteDS.StatTile` (bundle loaded from the root `_ds_bundle.js`).

Stat display used by ElectionCountdown's Days/Hrs/Mins/Secs boxes and
ImpactMetrics' headline-number row.

## Props

```ts
interface StatTileProps {
  /** The big number/value (e.g. a countdown digit or a metric total). */
  value: React.ReactNode;
  /** Small caption below the value. */
  label: React.ReactNode;
  /** "tile" = bordered rounded box (ElectionCountdown digits). "bare" = no box, just stacked text (ImpactMetrics stat row). */
  variant?: "tile" | "bare";
  /** "sm" matches ElectionCountdown's compact digit boxes; "lg" matches ImpactMetrics' headline stat numbers. */
  size?: "sm" | "lg";
  className?: string;
  id?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}
```
