Tooltip from @smartervote/design-system. Use via `window.SmarterVoteDS.Tooltip` (bundle loaded from the root `_ds_bundle.js`).

Click-to-open popover — the interaction pattern behind
ValidationGradeBadge's info panel and IssueTable's renamed-issue
tooltips: a backdrop closes it on outside click, Escape closes it too.

## Props

```ts
interface TooltipProps {
  /** The element that toggles the popover open when clicked. */
  trigger: React.ReactNode;
  /** Popover panel content. */
  children: React.ReactNode;
  /** Which edge the panel hangs from. Defaults to "left". */
  align?: "left" | "right";
  className?: string;
}
```
