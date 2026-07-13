ElectionCountdown from @smartervote/design-system. Use via `window.SmarterVoteDS.ElectionCountdown` (bundle loaded from the root `_ds_bundle.js`).

Election-day countdown banner — a live Days/Hrs/Mins/Secs tile row while
upcoming, or a status pill ("Polls Open" / "Voting Closed") once the date
has passed.

## Props

```ts
interface ElectionCountdownProps {
  electionDate: string;
}
```
