SiteFooter from @smartervote/design-system. Use via `window.SmarterVoteDS.SiteFooter` (bundle loaded from the root `_ds_bundle.js`).

Site footer — wordmark + tagline, nav links, an amber AI-disclosure
notice box, and a copyright line.

## Props

```ts
interface SiteFooterProps {
  links: SiteFooterLink[];
  /** AI-disclosure notice text. Defaults to SmarterVote's standard notice. */
  aiNotice?: React.ReactNode;
}
```
