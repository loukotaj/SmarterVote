RaceCard from @smartervote/design-system. Use via `window.SmarterVoteDS.RaceCard` (bundle loaded from the root `_ds_bundle.js`).

Race summary card — office/jurisdiction badges, title, a row of
candidate avatars (party-ring colored), and a "View race" footer link.
The election-directory grid is built from a list of these.

## Props

```ts
interface RaceCardProps {
  race: RaceCardData;
  /** Link target. Defaults to "/races/{race.id}". */
  href?: string;
}
```
