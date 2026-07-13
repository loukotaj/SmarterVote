EmptyState from @smartervote/design-system. Use via `window.SmarterVoteDS.EmptyState` (bundle loaded from the root `_ds_bundle.js`).

Friendly "no data yet" block — generalized from NoDataFallback, which
SmarterVote uses when a candidate is missing issues/donor/voting data.

## Props

```ts
interface EmptyStateProps {
  /** Main message explaining what's missing. */
  message: React.ReactNode;
  /** Optional smaller supporting text below the action. */
  helpText?: React.ReactNode;
  /** Optional CTA link (e.g. "Help improve this data"). */
  action?: EmptyStateAction;
}
```
