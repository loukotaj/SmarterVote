VoterResources from @smartervote/design-system. Use via `window.SmarterVoteDS.VoterResources` (bundle loaded from the root `_ds_bundle.js`).

Row of external-resource CTA chips (Ballotpedia, Register to Vote, How
to Vote, and — when a forecast exists — a same-page jump link). Each
chip carries its own fixed semantic color, not the generic Button
variants, matching the original.

## Props

```ts
interface VoterResourcesProps {
  ballotpediaUrl?: string;
  registerToVoteUrl?: string;
  howToVoteUrl?: string;
  hasForecast?: boolean;
  onJumpToForecast?: () => void;
}
```
