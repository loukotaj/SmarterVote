Tabs from @smartervote/design-system. Use via `window.SmarterVoteDS.Tabs` (bundle loaded from the root `_ds_bundle.js`).

Underline tab bar — the CandidateCard body switcher (Issues / Background
/ Donors / Voting). Controlled: the parent owns `value` and swaps the
panel content itself; Tabs only renders the row of buttons.

## Props

```ts
interface TabsProps {
  items: TabItem[];
  /** Currently selected tab value (controlled). */
  value: string;
  onChange: (value: string) => void;
  style?: React.CSSProperties;
  className?: string;
  id?: string;
  children?: React.ReactNode;
}
```
