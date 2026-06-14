# Cloudflare Pages Migration Plan

Last reviewed: 2026-06-14.

## Objective

Move the public web app from GitHub Pages to Cloudflare Pages so the site has better edge delivery, cleaner SEO control, and a more direct deployment path.

This plan covers the web frontend, CI/CD, DNS, SEO metadata, and validation. It does not change the rule that race data is published separately from draft data.

## Why Change

- Cloudflare Pages gives better control over custom-domain hosting and redirects than GitHub Pages.
- The current GitHub Pages workflow is tied to a static deploy step and extra packaging workarounds.
- SEO quality depends on consistent canonical URLs, metadata, and sitemap behavior across the deployed host.
- A Cloudflare-hosted frontend aligns with the existing Cloudflare Web Analytics usage already present in the app.

## Current State

- The frontend uses SvelteKit static output via [web/svelte.config.js](../web/svelte.config.js).
- The web package still has GitHub Pages deployment scripts in [web/package.json](../web/package.json).
- CI currently validates the web app in [/.github/workflows/ci.yaml](../.github/workflows/ci.yaml).
- Deployment to GitHub Pages is handled in [/.github/workflows/WebDeploy.yml](../.github/workflows/WebDeploy.yml).
- The site already ships SEO assets such as [web/static/robots.txt](../web/static/robots.txt) and [web/static/sitemap.xml](../web/static/sitemap.xml).

## Target State

- Cloudflare Pages is the production host for the public web frontend.
- GitHub Pages deployment is removed or disabled.
- The web build still produces static prerendered output, but it is published by Cloudflare Pages instead of GitHub Pages tooling.
- Canonical URLs, Open Graph tags, and sitemap entries all point to the Cloudflare-served production domain.
- CI still validates the site before deployment, and CD is triggered only after successful checks.

## Workstreams

### 1. Frontend Build Output

Goal: keep the SvelteKit app static-host friendly without GitHub Pages-specific hacks.

Tasks:

- Keep the static adapter in [web/svelte.config.js](../web/svelte.config.js).
- Remove the GitHub Pages packaging step that copies `index.html` to `404.html` and writes `.nojekyll`.
- Keep prerendered routes and static assets intact.
- Confirm client-side routing works under Cloudflare Pages without relying on GitHub Pages fallback behavior.

Acceptance:

- `npm run build` still succeeds.
- The generated output works on the Cloudflare Pages preview domain.
- No GitHub Pages-only artifacts are required for deployment.

### 2. CI/CD Cutover

Goal: replace the current GitHub Pages deploy workflow with a Cloudflare Pages deploy workflow.

Tasks:

- Remove or retire [/.github/workflows/WebDeploy.yml](../.github/workflows/WebDeploy.yml).
- Add a new Cloudflare Pages deployment workflow.
- Keep CI checks in [/.github/workflows/ci.yaml](../.github/workflows/ci.yaml) as the gate before deployment.
- Configure the deploy workflow to run only after the main branch CI succeeds or from an explicit manual trigger.
- Pass the same production env vars used by the current web build, including API and analytics values.

Recommended deploy flow:

1. CI runs on pull requests and pushes to `main`.
2. Web build and tests pass.
3. Cloudflare Pages deploy runs from the verified commit.
4. Cloudflare serves the new production build behind the custom domain.

Acceptance:

- The old GitHub Pages deploy path is no longer authoritative.
- The new workflow is reproducible and reviewable in GitHub.
- Deployment failures are visible in CI/CD logs before any DNS switch.

### 3. Cloudflare Setup

Goal: make Cloudflare Pages the actual public hosting target.

Tasks:

- Create or repoint the Cloudflare Pages project for the repo.
- Connect the project to the web build output directory.
- Set production and preview environment variables.
- Attach the custom domain `smarter.vote`.
- Verify SSL/TLS, caching, and routing behavior for static assets and prerendered pages.

Acceptance:

- The production hostname resolves to Cloudflare Pages.
- Static assets load correctly.
- Deep links such as race and candidate routes resolve without client-side errors.

### 4. SEO Hardening

Goal: make the migration improve search visibility instead of just changing hosts.

Tasks:

- Confirm every major route has route-specific title and description metadata.
- Add or verify canonical URLs where the page should have a single preferred indexable URL.
- Ensure Open Graph and Twitter tags reflect the current page, not the homepage default.
- Confirm robots and sitemap files reference the final production domain.
- Check that prerendered candidate and race pages expose the correct share metadata.

Files most likely to need review:

- [web/src/routes/+page.svelte](../web/src/routes/+page.svelte)
- [web/src/routes/about/+page.svelte](../web/src/routes/about/+page.svelte)
- [web/src/routes/races/[slug]/+page.svelte](../web/src/routes/races/[slug]/+page.svelte)
- [web/src/routes/races/[slug]/[candidate]/+page.svelte](../web/src/routes/races/[slug]/[candidate]/+page.svelte)
- [web/src/routes/races/[slug]/compare/+page.svelte](../web/src/routes/races/[slug]/compare/+page.svelte)

Acceptance:

- Page titles are unique and descriptive.
- Share metadata matches the page being rendered.
- Sitemap entries stay aligned with the live domain.

### 5. Analytics and Tracking

Goal: preserve the existing analytics behavior during the hosting change.

Tasks:

- Keep the Cloudflare Web Analytics beacon wiring in [web/src/routes/+layout.svelte](../web/src/routes/+layout.svelte).
- Reconfirm the production analytics token in the Cloudflare Pages environment.
- Make sure admin routes do not load the public beacon if that remains the intended behavior.

Acceptance:

- Public page analytics continue to work after the cutover.
- Admin traffic is still handled according to the current layout logic.

### 6. Validation and Rollback

Goal: make the migration safe to cut over and safe to undo.

Tasks:

- Run the web checks before changing deploy targets.
- Build the site and inspect the output for a few representative routes.
- Test the Cloudflare Pages preview deployment before switching the custom domain.
- Verify the canonical domain, sitemap, and robots files after deployment.
- Keep a rollback path to the previous GitHub Pages or current stable deployment until the Cloudflare rollout is confirmed.

Validation checklist:

- `cd web && npm ci && npm run check && npm run build && npm run test:unit -- --run`
- Confirm homepage, about page, a race page, and a candidate page render correctly on the Pages preview URL.
- Confirm `robots.txt` and `sitemap.xml` are reachable on the new host.
- Confirm the custom domain resolves to the new deployment.

Rollback checklist:

- Repoint the custom domain to the last known good host if the new deploy fails.
- Re-enable the previous deploy workflow only if the Cloudflare path is not ready.
- Leave the web app source intact so the host can be switched again without code rollback.

## Delivery Order

1. Remove GitHub Pages-specific build and deploy steps.
2. Add Cloudflare Pages deployment workflow.
3. Verify build output, routing, and preview deployment.
4. Audit and fix metadata for SEO correctness.
5. Switch the custom domain to Cloudflare Pages.
6. Remove any old GitHub Pages references from docs and scripts.

## Risks

- A route that depends on GitHub Pages fallback behavior could break if it is not properly prerendered or routed.
- Metadata defaults can silently undermine SEO if they are not route-specific.
- Environment variables must be mirrored between local development, CI, and Cloudflare Pages.
- The deploy workflow must keep using the production-safe API and analytics settings.

## Done When

- Cloudflare Pages is the only production host for the public frontend.
- GitHub Pages deployment is no longer part of the release path.
- Search metadata, sitemap, and robots files match the production domain.
- CI validates the frontend before deployment, and CD publishes the verified build.
