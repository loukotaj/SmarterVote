SiteHeader from @smartervote/design-system. Use via `window.SmarterVoteDS.SiteHeader` (bundle loaded from the root `_ds_bundle.js`).

Sticky translucent site header — wordmark, primary nav, a pill search
box, and the light/dark toggle. The live autocomplete dropdown behind
search is app-specific routing logic (not ported); pass `searchResults`
to compose one.

## Props

```ts
interface SiteHeaderProps {
  links: SiteHeaderLink[];
  darkMode?: boolean;
  onToggleDark?: () => void;
  searchPlaceholder?: string;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  /** Rendered below the search box when non-empty — the results dropdown (Elections/Candidates groups). Left as a slot so the */
  searchResults?: React.ReactNode;
}
```
