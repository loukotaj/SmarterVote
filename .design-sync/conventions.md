## Smarter.Vote design system conventions

**Wrapping & dark mode.** No provider/root wrapper is required — every component works standalone. Dark mode is a plain Tailwind `class` strategy: wrap any subtree in an element with the literal class `dark` (e.g. `<div class="dark"> ... </div>`) to switch it into dark styling; there is no `ThemeProvider` and no other setup. A background color alone does nothing — `dark:` variants and the semantic tokens below only flip when an ancestor actually carries the `dark` class.

**Styling idiom: Tailwind utility classes over semantic tokens.** Every component is styled with plain Tailwind classes — no CSS-in-JS, no separate stylesheet to hand-author, no arbitrary hex values. Compose new layout/spacing with ordinary Tailwind utilities (`flex`, `gap-4`, `rounded-lg`, `p-6`, `shadow-sm`, …) and reach for these semantic color classes instead of raw grays/blues so new UI matches the brand and repaints correctly in dark mode:

| Class | Use | Light | Dark |
|---|---|---|---|
| `bg-surface` | cards, panels | `#FFFFFF` | `#111827` |
| `bg-surface-alt` | subtle/inset surfaces | `#F3F4F6` | `#1F2937` |
| `border-stroke` | default borders | `#E5E7EB` | `#374151` |
| `text-content` | primary text | `#111827` | `#F9FAFB` |
| `text-content-muted` | secondary text | `#4B5563` | `#D1D5DB` |
| `text-content-subtle` | tertiary text | `#6B7280` | `#9CA3AF` |
| `text-content-faint` | placeholder/meta text | `#9CA3AF` | `#6B7280` |
| `text-primary-600` | brand-colored text (eyebrows, links) | `#2563EB` | pair with `dark:text-primary-500` |

For page-level background (not used inside components, only for a host page wrapping them), the same token scheme defines `--sv-page` (`#F9FAFB` light / `#030712` dark) as a CSS custom property, but no component ships a `bg-page` utility — apply `background-color: rgb(var(--sv-page))` directly if needed. The brand accent otherwise is Tailwind's stock `blue-600`/`blue-700` (buttons, links, focus rings — see `Button`'s `primary` variant) — don't invent a different blue. Status/semantic colors (grade badges, confidence indicators, office-type chips) use the standard Tailwind palette directly (`green`, `red`, `yellow`, `orange`, `purple`, `teal`, `indigo`, `emerald`, `amber`, `rose`) at the `-100`/`-600`/`-800` steps with `dark:` counterparts at `-900/40`–`-200` — see `Badge`'s `tone` prop for the canonical set. Border radius scales by role: `rounded-lg` for buttons/inputs, `rounded-xl`/`rounded-2xl` for cards and hero panels, `rounded-full` for pills/badges/avatars. Font is **Inter** (400/500/600/700, self-hosted — no `<link>` needed, it ships in the bundle).

**Where the truth lives.** Read `styles.css` and its import chain (`_ds_bundle.css` — the compiled Tailwind output containing every utility class and the `:root`/`.dark` token custom properties shown above; `fonts/fonts.css` — the Inter `@font-face` rules) before styling anything by hand. Each component's `.prompt.md` is its real usage reference — read it for the exact prop shapes (e.g. `CandidateCard`'s `candidate` object, `RaceCard`'s `race` object) rather than guessing.

**Composition example** (a filter row + card, using only the vocabulary above):

```tsx
import { Badge, Card, Button } from "@smartervote/design-system";

<div className="flex flex-col gap-3">
  <div className="flex gap-2">
    <Button variant="pill" active>All Races</Button>
    <Button variant="pill">Senate</Button>
    <Button variant="pill">Governor</Button>
  </div>
  <Card className="p-4">
    <Badge tone="blue" size="sm">Senate</Badge>
    <h3 className="mt-2 text-lg font-semibold text-content">Georgia U.S. Senate</h3>
    <p className="mt-1 text-sm text-content-muted">3 candidates researched</p>
  </Card>
</div>
```
