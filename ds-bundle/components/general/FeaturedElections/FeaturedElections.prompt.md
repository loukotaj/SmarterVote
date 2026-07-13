FeaturedElections from @smartervote/design-system. Use via `window.SmarterVoteDS.FeaturedElections` (bundle loaded from the root `_ds_bundle.js`).

Homepage "recently updated" editorial section — one large featured race
beside a compact list of the next few. Renders nothing when `races` is empty.

## Props

```ts
interface FeaturedElectionsProps {
  /** First race is the large "Featured" story; up to 4 more render as the side list. */
  races: FeaturedElectionsRace[];
}
```
