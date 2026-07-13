SourceLink from @smartervote/design-system. Use via `window.SmarterVoteDS.SourceLink` (bundle loaded from the root `_ds_bundle.js`).

Inline external-source citation link — an icon-suffixed underline link
that opens in a new tab, with a domain fallback label. Renders as plain
text (no link) for any non-http(s) URL.

## Props

```ts
interface SourceLinkProps {
  /** Source URL. Only http/https URLs render as a link — anything else falls back to plain text. */
  url: string;
  /** Optional source title, used for the label and title-attribute fallback. */
  title?: string;
  /** Explicit label override. Falls back to title, then the URL's domain. */
  text?: string;
}
```
