TrustPrinciples from @smartervote/design-system. Use via `window.SmarterVoteDS.TrustPrinciples` (bundle loaded from the root `_ds_bundle.js`).

Always-dark editorial section (bg-blue-950, white text) even when the
rest of the page is in light mode — SmarterVote's "editorial promise"
block on the homepage.

## Props

```ts
interface TrustPrinciplesProps {
  eyebrow?: string;
  heading?: React.ReactNode;
  description?: string;
  ctaHref?: string;
  ctaLabel?: string;
  principles?: TrustPrinciple[];
}
```
