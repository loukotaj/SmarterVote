ValidationGradeBadge from @smartervote/design-system. Use via `window.SmarterVoteDS.ValidationGradeBadge` (bundle loaded from the root `_ds_bundle.js`).

Circular A–F AI-validation grade pill. Clicking it opens a popover with
the score, a summary, and a "View Full Review" link.

## Props

```ts
interface ValidationGradeBadgeProps {
  grade: ValidationGradeInfo;
  /** Called when the user clicks "View Full Review" inside the popover. */
  onViewReview?: () => void;
}
```
