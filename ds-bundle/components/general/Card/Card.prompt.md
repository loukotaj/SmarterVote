Card from @smartervote/design-system. Use via `window.SmarterVoteDS.Card` (bundle loaded from the root `_ds_bundle.js`).

SmarterVote's base surface — a rounded, bordered panel used as the
foundation for every card-like composite (CandidateCard, RaceCard, etc).

## Props

```ts
interface CardProps {
  /** HTML element to render as. Defaults to "div". */
  as?: "symbol" | "object" | "a" | "abbr" | "address" | "area" | "article" | "aside" | "audio" | "b" | "base" | "bdi" | "bdo" | "big" | "blockquote" | "body" | (string & {}) /* +162 more */;
  className?: string;
  id?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}
```
