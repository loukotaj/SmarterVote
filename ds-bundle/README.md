# SmarterVoteDS (@smartervote/design-system@0.1.0)

This design system is the published @smartervote/design-system React library, bundled as a single
browser global. All 22 components are the real upstream code.

## Where things are

- `_ds_bundle.js` — the whole-DS bundle at the project root; loads every component to `window.SmarterVoteDS`. First line is a `/* @ds-bundle: … */` metadata header.
- `styles.css` — the single stylesheet entry: it `@import`s the tokens, fonts, and component styles (`_ds_bundle.css`). Link this one file.
- `components/<group>/<Name>/<Name>.prompt.md` (example JSX + variants), `<Name>.d.ts` (types), `<Name>.html` (variant grid).
- `tokens/*.css` — CSS custom properties, names verbatim from upstream.
- `fonts/` — `@font-face` files + `fonts.css` (when the package ships fonts).

For a specific component, `read_file("components/<group>/<Name>/<Name>.prompt.md")`.

## Loading

Add these two lines to your page once (React must be on the page first):

```html
<link rel="stylesheet" href="styles.css">
<script src="_ds_bundle.js"></script>
```

Components are then available at `window.SmarterVoteDS.*`. Mount into a dedicated child node (e.g. `<div id="ds-root">`), not the host page's own React root, so the two trees don't collide:

```jsx
const { Avatar } = window.SmarterVoteDS;
ReactDOM.createRoot(document.getElementById('ds-root')).render(<Avatar />);
```

## Tokens

72 CSS custom properties from @smartervote/design-system. Names are
preserved verbatim from upstream. They are declared inside `_ds_bundle.css` (this DS ships one compiled stylesheet rather than separate token files).

- **color** (14): `--sv-surface`, `--sv-surface-alt`, `--sv-text-muted`, …
- **spacing** (2): `--tw-ring-inset`, `--tw-space-y-reverse`
- **shadow** (4): `--tw-ring-offset-shadow`, `--tw-ring-shadow`, `--tw-shadow`, …
- **other** (52): `--sv-page`, `--sv-border`, `--sv-text`, …

## Components

### general
- `Avatar` — Circular candidate/user avatar  photo when available, otherwise
- `Badge` — Generic colored pill  generalizes the grade (AF), confidence
- `Button` — SmarterVote's button  synthesized from the repeated Tailwind class
- `CandidateCard` — The candidate profile card  the app's most visually dense composite.
- `Card` — SmarterVote's base surface  a rounded, bordered panel used as the
- `ConfidenceIndicator` — Glowing-dot confidence pill (high/medium/low/unknown) used throughout
- `ElectionCountdown` — Election-day countdown banner  a live Days/Hrs/Mins/Secs tile row while
- `EmptyState` — Friendly no data yet block  generalized from NoDataFallback, which
- `FeaturedElections` — Homepage recently updated editorial section  one large featured race
- `HowItWorks` — Three-step numbered explainer section, each step with a top border
- `ImpactMetrics` — Coverage-stats strip (guides published, candidate profiles, states
- `RaceCard` — Race summary card  office/jurisdiction badges, title, a row of
- `SectionHeader` — Eyebrow / title / description page-header pattern, used at the top of
- `SiteFooter` — Site footer  wordmark + tagline, nav links, an amber AI-disclosure
- `SiteHeader` — Sticky translucent site header  wordmark, primary nav, a pill search
- `SourceLink` — Inline external-source citation link  an icon-suffixed underline link
- `StatTile` — Stat display used by ElectionCountdown's Days/Hrs/Mins/Secs boxes and
- `Tabs` — Underline tab bar  the CandidateCard body switcher (Issues / Background
- `Tooltip` — Click-to-open popover  the interaction pattern behind
- `TrustPrinciples` — Always-dark editorial section (bg-blue-950, white text) even when the
- `ValidationGradeBadge` — Circular AF AI-validation grade pill. Clicking it opens a popover with
- `VoterResources` — Row of external-resource CTA chips (Ballotpedia, Register to Vote, How
