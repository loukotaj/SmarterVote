SectionHeader from @smartervote/design-system. Use via `window.SmarterVoteDS.SectionHeader` (bundle loaded from the root `_ds_bundle.js`).

Eyebrow / title / description page-header pattern, used at the top of
every support/policy page (TrustPage) and section intros.

## Props

```ts
interface SectionHeaderProps {
  /** Small uppercase label above the title (e.g. "Smarter.Vote"). */
  eyebrow?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
}
```
