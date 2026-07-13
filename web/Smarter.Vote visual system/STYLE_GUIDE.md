# Smarter.Vote Style Guide

The editable visual reference is `Smarter.Vote Brand Assets.dc.html`. Open it directly in a browser to review the logo, social compositions, typography, color palette, UI patterns, and example data graphics. The HTML is the source of truth; exported images should be produced only when needed and should not be committed here.

## Brand idea

Smarter.Vote presents election information as calm, legible evidence. The check-shaped trend line and its white endpoint combine civic completion with a visible data point. Interfaces should feel analytical without becoming clinical or partisan.

Use the name as `Smarter.Vote`, including the period. The primary supporting line is `Know Your Candidates`.

## Logo

- Use the dark rounded-square mark as the primary app icon and avatar.
- Keep the blue trend line and white endpoint intact; do not recolor individual elements.
- Use the complete wordmark where horizontal space allows.
- On light backgrounds, use the dark wordmark with the medium-blue period.
- Preserve clear space around the mark and avoid placing it over visually busy imagery.

## Color

| Role | Value | Usage |
| --- | --- | --- |
| Canvas | `#060D1A` | Deepest page background |
| Brand navy | `#0E1D38` | Logo field and elevated dark surfaces |
| Surface | `#0B1830` | Cards and panels |
| Subtle surface | `#132445` | Tracks and nested regions |
| Border | `#1B2E4D` | Default dark-theme borders |
| Brand blue | `#4FB3FF` | Primary accent, links, and logo trend line |
| Brand blue hover | `#8FCBFF` | Interactive hover state |
| Primary text | `#FFFFFF` | High-emphasis text on dark backgrounds |
| Secondary text | `#C6D4E8` | Body copy on dark backgrounds |
| Muted text | `#8FA5C4` | Labels and supporting copy |
| Quiet text | `#5B6B84` | Metadata and low-emphasis annotations |
| Light canvas | `#F4F7FB` | Light-background applications |

Blue is the product accent, not a party indicator. Political affiliation colors should remain secondary and appear only with explicit text labels.

## Typography

- Use Archivo for headlines, navigation, controls, and body copy. Favor weights 500 through 800.
- Use IBM Plex Mono for metadata, dates, source labels, compact status text, and technical annotations.
- Prefer direct sentence case. Uppercase mono labels may be used sparingly for short categories.
- Keep long-form copy comfortably spaced and avoid overly compressed line lengths.

The HTML source loads both families from Google Fonts and shows the intended hierarchy at production-like sizes.

## Surfaces and controls

- Use dark navy surfaces with restrained one-pixel borders.
- Use moderate rounded corners; cards generally use a larger radius than buttons or labels.
- Reserve bright blue for actions, links, focus, and essential emphasis.
- Show sources, timestamps, confidence, and methodology close to the claims they qualify.
- Prefer comparison layouts that give candidates equal visual weight.

## Data and political content

- Pair color with names or party labels; never rely on color alone.
- Distinguish forecasts and estimates from confirmed results.
- Include the update time and evidence source when presenting changing data.
- Avoid visual treatments that imply endorsement, certainty, or false precision.
- Use fictional names and races in reusable promotional templates unless publication data has been approved.

## Asset workflow

Edit the HTML source when the brand system changes. When a platform needs a raster asset, capture the specifically labeled canvas at its stated pixel dimensions and store the delivered asset outside this source folder. The deployed Open Graph image remains under `web/static/` because it is a runtime web asset.
