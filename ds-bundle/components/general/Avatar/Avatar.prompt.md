Avatar from @smartervote/design-system. Use via `window.SmarterVoteDS.Avatar` (bundle loaded from the root `_ds_bundle.js`).

Circular candidate/user avatar — photo when available, otherwise
initials on a blue tint (the fallback used throughout CandidateCard
and RaceCard). Wrap in an element with a `ring-*` class for the
party-colored ring RaceCard applies around each candidate thumbnail.

## Props

```ts
interface AvatarProps {
  /** Full name — used to derive initials when no image is provided. */
  name: string;
  /** Optional photo URL. Falls back to initials-on-blue when omitted or broken. */
  src?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
  id?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}
```
