CandidateCard from @smartervote/design-system. Use via `window.SmarterVoteDS.CandidateCard` (bundle loaded from the root `_ds_bundle.js`).

The candidate profile card — the app's most visually dense composite.
Header (avatar, name, party/incumbent badges, summary) is always
visible; "Show More" reveals a tabbed detail section (Key Issues,
Background, Donors, Voting Record).

## Props

```ts
interface CandidateCardProps {
  candidate: CandidateCardData;
  /** Link target for the candidate's name — omit to render as plain text. */
  href?: string;
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: () => void;
  /** Whether the tabbed detail section starts open. Defaults to false. */
  defaultExpanded?: boolean;
}
```
