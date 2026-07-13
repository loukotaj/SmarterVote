# Homepage and Sponsorship Redesign Implementation Plan

**Status:** Partially implemented
**Last reviewed:** 2026-07-12
**Scope:** Product and engineering plan with delivery status; remaining phases are not implied to be implemented

### Implementation status (2026-07-12)

Delivered in the initial national-only release slice:

- Redesigned homepage with **Explore national elections**, honest state/local coverage limits, real-data featured elections and metrics, and research/trust/support sections.
- Dedicated `/elections/` national directory using the existing map, search, and filters.
- Reusable site header/footer and public routes for methodology, corrections, privacy, terms, support, partners, funding/editorial independence, and an improved About page.
- Static-route prerendering, sitemap/robots integration, canonical architecture/document-map updates, and focused frontend tests.

Still gated and not implemented: address/ballot lookup, Google Places/Census integration, contest-provider catalog/matching, live contribution checkout, Stripe/webhooks, partner form/CRM delivery, and payment infrastructure. These remain subject to the funding, provider, privacy, legal, and LLC-readiness gates below.

### Owner decisions recorded 2026-07-12

- Initial public coverage is national/federal election research only. Local, judicial, county, municipal, and ballot-measure discovery is deferred until funding supports a dependable data provider.
- No election provider is selected or affordable today. Provider evaluation remains a funded future phase, not a launch blocker for the redesigned informational homepage.
- Smarter.Vote LLC is the accountable organization. Until named people/roles or separate aliases exist, corrections, privacy, refunds, and partnerships route to `SmarterDotVote@gmail.com` with role-based labels on the site.
- Lookup results should use browser memory/`sessionStorage`; no server-side result persistence is planned. The existing scale-to-zero API may eventually proxy a lookup transaction, but it must not retain a result record.
- Partner and correction inquiries use the Gmail inbox initially, with minimal collection and documented retention.
- Existing GitHub Sponsors support does not need migration. A low-prominence **Support the developer** link may remain on the improved About page; `/support/` is the future Smarter.Vote LLC funding path.
- The LLC, payment, legal, and physical-mail setup is not ready for live payment activation. The plan describes the target state; content/inquiries can precede payments.
- Any future Google autocomplete pilot has a **$10/month target operating budget** and a default quota of **250 autocomplete requests/day** (approximately 7,500 in a 30-day month). The owner responds manually to billing alerts; no custom billing kill switch is required. Direct Census address entry remains the normal fallback when Google is unavailable or its configured quota is reached.

## 1. Executive summary

Smarter.Vote should change from a race directory with an AI warning into a guided civic-information product. The national-only launch should first explain the value, make **Explore national elections** the primary action, show a real preview from published data, explain the research and review process, establish limits and editorial standards, and then offer support paths. Once funded address-specific coverage passes its release gates, **Find my ballot** replaces it as the primary action. The full directory remains valuable at a dedicated `/elections/` route.

Address lookup should not launch while the product covers only national races: an address adds no useful targeting and would imply local-ballot knowledge the product does not have. The first release should say **Explore national elections**, while preserving **Find my ballot** as the approved future CTA once address-specific federal/state coverage meets its launch gate. That later lookup must not be presented as an official or complete ballot. It is a five-stage system: address autocomplete, geocoding/normalization, district resolution, election identification, and matching those elections to Smarter.Vote research. No election provider is selected today; local/judicial/measure discovery is explicitly funding-dependent. Google Places plus Census is a research candidate, not an approved combination, because current Google Places policies restrict storage/use of Places content and do not clearly authorize passing Google-derived address content into a separate Census workflow. Before implementation, obtain qualified review or written provider confirmation; otherwise use a contractually compatible input/geocoder pair or direct Census address entry.

Future lookup results should use four exact states: **Research available**, **Election identified — research in progress**, **Check official election information**, and **We may not have identified every contest**. The page title should be “Elections near you,” never “Your complete ballot.” Full addresses must not appear in URLs, Firestore, analytics, logs, error reports, or durable browser storage. The backend should receive an address only for the shortest practical lookup transaction, redact it before telemetry, return results directly, and persist no result token or lookup record. Browser memory with expiring `sessionStorage` is sufficient for refresh continuity.

Public support should live at `/support/`; institutional material should live at `/partners/`. The support page serves individuals and time-limited campaigns, while the partners page serves sponsors, newsrooms, universities, nonprofits, grantmakers, and data/API partners. Stripe-hosted Checkout is the recommended payment surface for one-time and monthly support; Stripe invoices are used for negotiated institutional agreements. No account is required. Smarter.Vote LLC must clearly state that contributions are not tax-deductible. Funding may prioritize a geography or coverage category only through a published, standards-based queue; it may never change findings, sources, classifications, forecasts, or publication decisions.

The work should ship behind staged data-quality and privacy gates. A polished homepage and trust pages can launch before lookup. Address lookup should not become the primary CTA until the pilot meets match-quality, official-link, privacy, accessibility, and cost thresholds.

## 2. Current-state assessment

### Application and delivery

- `web/` is SvelteKit 2/Svelte 4 with TypeScript, Tailwind CSS, semantic light/dark tokens, Vitest, Testing Library, and the static adapter. Cloudflare Pages hosts the generated site.
- Public pages normally read `races/summaries.json` and individual published race JSON directly from GCS through `VITE_PUBLIC_DATA_URL`. SvelteKit prerenders routes during the Cloudflare build.
- `services/races-api/` is the canonical FastAPI service on Cloud Run. It owns public API fallbacks, Auth0-protected administration, Firestore access, rate limiting, and API analytics. Secret Manager supplies service secrets.
- GCS owns draft, published, retired, artifact, and checkpoint objects. Firestore owns the race catalog and operational records. Auth0 is admin-only; public users have no account model.
- Cloudflare Web Analytics records static-page traffic. The API separately hashes IP addresses for operational analytics. Neither system currently models product events such as lookup completion or support conversion.
- GitHub Actions runs frontend checks/tests/build, Python tests/format checks, Terraform validation, and deploy workflows. GCP/deployed behavior remains the source of truth and CI is the release gate.

### Existing public experience

- `web/src/routes/+page.svelte` is a large directory: alpha warning, “Know your candidates,” candidate/office/state search, interactive US map, filters, and every published `RaceCard`.
- There is no `/elections/` route, address lookup, result session, geocoder, boundary resolver, election catalog, support page, partner page, privacy page, terms page, methodology page, corrections workflow page, or funding policy page.
- `web/src/routes/+layout.svelte` contains duplicated mobile/desktop navigation, global race/candidate autocomplete, theme switching, Auth0-aware admin links, and the Cloudflare beacon. The footer/navigation expose Home, About, Forecasts, GitHub, and GitHub Sponsors.
- `web/src/routes/about/+page.svelte` contains mission, pipeline, limitations, no-endorsement language, GitHub issue CTA, and an embedded GitHub Sponsors card. It repeatedly claims “unbiased,” over-centers AI, calls the project self-funded/one-person, and says nonprofit rather than the intended Smarter.Vote LLC status.
- Race pages already provide strong reusable proof: candidate cards, issue positions, confidence indicators, source links, updated timestamps, forecasts, voter resources, comparisons, missing-data fallbacks, and issue-report links. Current missing-data links and race-page sponsorship links point to GitHub.
- `RaceCard`, `CandidateCard`, `IssueTable`, `ConfidenceIndicator`, `SourceLink`, `VoterResources`, `NoDataFallback`, `Card`, and forecast utilities are reusable, but should gain compact/presentation variants rather than be copied into homepage-only markup.

### Data strengths and constraints

- `shared/models.py`/`web/src/lib/types.ts` define rich researched-race data: identity, election date, candidates, positions, sources, confidence, polling, forecast, roster sources, voter resources, and timestamps.
- Published summaries support ID, title, office, jurisdiction, state, election date, update time, candidates, and forecast fields. Summary shaping can derive quality/freshness, but the checked-in `web/static/summaries.json` does not currently expose district, quality, or freshness.
- The checked-in snapshot contains 508 races, 1,877 candidate entries, and all 50 states; these counts are a local fixture/snapshot, not a production guarantee or proof of ballot completeness. Metrics must be computed from deployed published data at build/request time and labeled with an “as of” date.
- Current race IDs are human slugs and metadata lacks normalized identifiers such as state FIPS, office type, chamber, district number/GEOID, election ID, election stage, county/municipality IDs, and provider IDs. Title/string matching is insufficient for address lookup.
- The current catalog contains researched/published races, not a universe of elections. It cannot distinguish an uncovered known contest from a contest the system never discovered.
- No address, ZIP, map-boundary, geocoding, Places, Census, Google Civic, Nominatim, Stripe, payment, webhook, or contribution implementation exists. An old planning document mentions Civic API, but it is not runtime code.
- Forecast availability is broad in the fixture, but forecast inclusion is inappropriate as a universal product-preview requirement, especially for local/nonpartisan contests and low-confidence data.

### Material technical/product debt

- Homepage responsibilities and global search logic are monolithic and duplicate office classification and filtering logic.
- Public API endpoints are decorated with `verify_token` even though production public traffic normally bypasses them through GCS; lookup/payment APIs need deliberately public, separately rate-limited contracts rather than accidental reuse.
- Cloudflare static hosting is excellent for public research, but personalized lookup and payment creation require dynamic API calls.
- “Unbiased” and multi-model accuracy language overstates guarantees. There is no consolidated methodology, correction, privacy, legal, or editorial-independence contract.
- Current analytics cannot reliably support “most viewed” election selection from static page views without a new event/dimension pipeline.

## 3. Product goals

1. Let a first-time visitor understand the service and reach relevant researched elections in under a minute.
2. Make coverage limits more noticeable than any implied completeness claim.
3. Demonstrate useful sourced research using real published data.
4. Establish trust through methods, citations, uncertainty, corrections, ownership, privacy, and funding independence.
5. Preserve fast, indexable static race pages and a browsable election directory.
6. Give individuals and institutions professional, legally accurate ways to support Smarter.Vote LLC.
7. Build lookup/provider boundaries that permit better ballot data without rewriting the frontend.
8. Measure utility, coverage gaps, lookup quality, and sustainable funding without collecting address histories.

## 4. Non-goals

- Claiming to reproduce an official sample ballot or every eligible contest.
- Voter registration, eligibility decisions, polling-place lookup, or election administration.
- Storing address books, user profiles, partisan preferences, or ballot selections.
- Launching candidate endorsements, personalized recommendations, ideological scoring, or sponsor-selected conclusions.
- Treating forecasts as applicable to every race or as the primary civic value.
- Replacing official election authorities, legal advice, or election-day verification.
- Creating supporter accounts in the initial payment release.
- Promising tax deductibility or representing the LLC as a nonprofit.
- Building a full CRM, grants platform, or data-licensing product before demand is validated.

## 5. User journeys

### First-time voter lookup

Visitor reads “Understand the elections where you live,” enters a street address, chooses a keyboard-accessible suggestion, accepts clear coverage/privacy copy, and selects **Find my ballot**. The result page groups matched researched elections first, known but unresearched elections second, and official resources/coverage warning last. The address is never rendered back or placed in the URL. The visitor opens a race, compares candidates, and follows citations.

### Ambiguous, rural, or unsupported address

The user sees which part failed without blame: “Choose a full street address,” “We found more than one match,” “We could not determine districts for this address,” or “No researched elections matched these districts.” They can retry, use manual state/district browsing, and open official election resources. A zero-match result is not described as “no elections.”

### Directory-first visitor

The user selects **Explore all elections**, lands at `/elections/`, and uses the existing map/search/filter experience. Directory URLs keep shareable non-sensitive filters. The homepage displays only a small, deterministic featured set.

### Individual supporter

The visitor lands on `/support/`, understands the LLC/non-deductibility and independence disclosures before paying, chooses one-time or monthly support, optionally elects public recognition, completes Stripe-hosted Checkout, and returns to a receipt/thank-you state. No Smarter.Vote account is required.

### Institutional partner

The visitor lands on `/partners/`, chooses sponsorship, newsroom/university/civic collaboration, grant funding, or data/API integration, reviews the independence policy, and submits a minimal inquiry. Negotiated funding uses a contract and Stripe invoice, not consumer contribution tiers.

### Correction reporter

From any trust or race page, the visitor opens a first-party correction form carrying only race/candidate/claim identifiers. The workflow acknowledges receipt, preserves editorial control, and eventually exposes a correction/update note where appropriate. GitHub remains an optional developer channel, not the public-facing requirement.

## 6. Recommended information architecture

| Route                                  | Purpose                                                        | Indexing                                        |
| -------------------------------------- | -------------------------------------------------------------- | ----------------------------------------------- |
| `/`                                    | Guided homepage and address entry                              | Index/canonical                                 |
| `/elections/`                          | Full current directory, map, text search, filters              | Index/canonical                                 |
| `/elections/near-you/`                 | Personalized lookup result shell using opaque session state    | `noindex, nofollow`; canonical to `/elections/` |
| `/races/[slug]/` and child routes      | Existing public research                                       | Index/canonical                                 |
| `/about/`                              | Mission, organization, team/ownership, project status          | Index/canonical                                 |
| `/methodology/`                        | Research, review, sources, uncertainty, forecasts, limitations | Index/canonical                                 |
| `/corrections/`                        | Correction policy and form                                     | Index/canonical                                 |
| `/support/`                            | Individual support and optional campaign module                | Index/canonical                                 |
| `/partners/`                           | Institutional sponsorships, grants, collaborations, data/API   | Index/canonical                                 |
| `/funding-and-editorial-independence/` | Durable funding, sponsor disclosure, conflict rules            | Index/canonical                                 |
| `/privacy/` and `/terms/`              | Legal/privacy contracts                                        | Index/canonical                                 |
| `/support/thanks/`                     | Payment return state                                           | `noindex`                                       |

Use `/support/` rather than `/sponsor/`: it is inclusive of individual recurring/one-time contributions without implying advertising. Keep `/partners/` separate because institutional due diligence, inquiry data, contracts, and language differ materially. Redirect old/future aliases `/sponsor/`, `/donate/`, and `/support-smarter-vote/` to `/support/`. Navigation should expose **Elections**, **Methodology**, **About**, and **Support**; place Forecasts under Elections or as a secondary desktop link. Footer should add Partners, Corrections, Funding & independence, Privacy, Terms, GitHub, and an organization disclosure.

## 7. Homepage content and section-by-section design

### 7.1 Hero and lookup

Recommended copy after funded lookup is ready:

> **Understand the elections where you live**
> Clear, sourced, nonpartisan candidate research—so you can compare what is known and verify it yourself.

Input label: **Home address**
Placeholder: **Start typing your street address**
Primary CTA: **Find my ballot**
Secondary CTA: **Explore all elections**

Immediately below the form:

> We use your address to identify relevant districts and do not save it. [How address privacy works](/privacy/).
> **Ballot coverage is currently incomplete. We are working to source additional federal, state, and local election data.** [Funding helps expand coverage](/support/#expand-coverage).

Retain “Find my ballot” as the future approved language because it matches voter intent, but pair it with the visible limitation and call the result “Elections near you.” For the initial national-only release, do **not** render a disabled address field or imply that an address changes the results. Use this launch hero instead:

> **Understand the elections shaping the country**
> Clear, sourced, nonpartisan candidate research for national elections. State and local ballot coverage is not available yet.
> Primary CTA: **Explore national elections**
> Secondary CTA: **Help expand coverage**

Optionally offer a simple “Notify me when ballot lookup launches” email link/form only after a retention and consent policy exists. Promote address lookup to the primary CTA only after Phase 3 acceptance criteria pass.

### 7.2 Product demonstration

Render one representative, currently published national race through a compact `ResearchPreview` composed from real race JSON. Do not select a race merely because it is competitive or famous. At build time, choose the most recently updated race that has a future election date; exactly two or three active candidates; at least two candidates with nonempty summaries and six issue positions each; source links for at least 80% of displayed positions; no low/unknown confidence in displayed rows; no stale flag; and a passing publication quality grade. Permit a small reviewed denylist/override for sensitive or visually poor examples. Show two candidates, two or three issue rows, inline source links, confidence/limited-data labels, and updated date. Add a forecast only when current and clearly distinguished from candidate research. If no race qualifies, omit the preview and show the directory CTA—never lower the threshold or use invented sample content.

CTA: **See the full comparison**. If preview data fails, show a small directory CTA rather than sample data in production.

### 7.3 How it works

Use three concise steps:

1. **Research** — Gather candidate statements, official records, reputable reporting, and other public sources.
2. **Review** — Compare evidence, flag conflicts, and run consistency/quality checks before publication.
3. **Verify** — Link claims to sources, show uncertainty and update dates, and accept corrections.

AI may be explained on `/methodology/` as part of the tooling. It should not be the section headline and must not imply that multiple models ensure accuracy.

### 7.4 Featured elections

Show 3–6 cards, not the full directory. Initial selection should be **Recently updated** because `updated_utc` is supported and auditable. Allow an explicit reviewed `featured_race_ids` configuration later, displaying “Featured” rather than implying popularity. “Most viewed” requires privacy-reviewed first-party event aggregation; “near you” belongs after lookup; “competitive” is allowed only where forecast ratings are current and should not dominate selection. Each algorithm needs deterministic eligibility, freshness thresholds, and fallback behavior.

### 7.5 Trust and methodology

Use a compact trust panel linking to durable policies:

- **Sourced:** important claims link to supporting material.
- **Transparent about limits:** uncertainty, sparse evidence, and update dates are visible.
- **Consistent standards:** the same research and review rules apply regardless of party.
- **Independent:** supporters cannot influence conclusions or coverage treatment.
- **Correctable:** readers can report errors; material updates are documented.

Copy should state: “Smarter.Vote is nonpartisan. We do not endorse candidates. We do not claim perfect neutrality or infallibility.” Replace “unbiased” across public metadata and trust copy with “sourced,” “transparent,” or “nonpartisan.”

### 7.6 Mission and impact

Explain the focus on credible information for overlooked as well as prominent elections. Initially display only metrics computed from deployed published data: **published national election guides**, **candidate profiles**, **states represented**, and **last updated**. Smarter.Vote LLC signs off through a dated metrics-definition record. Count only published, non-retired records; deduplicate candidate entries by `(race_id, normalized candidate name)` rather than implying unique people; count states from normalized state fields; and show both the newest published timestamp and metrics snapshot date. Add **sources linked** only after a tested canonical counting definition exists. Add **fully researched/limited-data races** only after a public coverage-state definition is persisted. Do not expose pipeline cost, tokens, raw quality grades, or “people reached” as impact.

Initial targets are operational: 100% of displayed metrics reproducible from deployed data; zero broken/stale homepage preview links; at least 99.5% successful static homepage loads; p75 mobile LCP below 2.5 seconds; zero critical accessibility findings; and all trust/legal links working. Do not set traffic, contribution, or conversion targets until four weeks of baseline data exists.

### 7.7 Support CTA

Use one restrained section after core civic value: “Help expand clear election coverage.” Mention data access, research/review, accessibility, and translation; link to `/support/` and `/partners/`. Repeat the no-editorial-influence promise in one sentence. Do not use donation thermometers or campaign aesthetics outside an active, clearly dated campaign module.

### 7.8 Visual system

Keep the current neutral surfaces, typography hierarchy, dark mode, blue action color, amber caution, and semantic tokens. Add semantic tokens for `coverage-available`, `coverage-pending`, `coverage-official`, `disclosure`, and `support` without mapping Democratic/Republican colors to global states. Prefer cards, rules, restrained data motifs, and real interface previews. Avoid decorative animation; any transition must honor reduced motion.

## 8. Address and ballot lookup architecture

### Decision matrix

| Layer                   | Recommendation                                                                                                                                                                                           | Why / tradeoff / migration                                                                                                                                                                                                                                                                                                   |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Autocomplete            | Deferred. Research Google Places Autocomplete (New) against a contractually compatible end-to-end provider; do not approve it merely on technical quality.                                               | Strong UX, but paid/vendor-dependent. Google requires public Terms/Privacy, attribution, and restricts storage of Places content except place IDs. Nominatim's public service is unsuitable for production autocomplete load; self-hosting creates operational burden. A plain address form may be the cheapest later pilot. |
| Geocoding/normalization | Prefer direct US Census Geocoding Services input for the first low-cost pilot. Use Google Places-derived content with Census only after qualified review or written confirmation permits the exact flow. | Census is free and US-focused, but match behavior and local geographies vary. Do not cache normalized addresses or coordinates; ephemeral processing makes a hash cache unnecessary.                                                                                                                                         |
| District identification | Census geographies for congressional and supported state legislative districts; provider/official crosswalks for county/municipal/judicial/special districts                                             | Separates boundary truth from election content. Do not infer districts from ZIP codes. Add a versioned boundary adapter so TIGER/Line point-in-polygon can replace/augment APIs later.                                                                                                                                       |
| Election identification | Deferred and unfunded. When funding exists, implement an `ElectionProvider` adapter and compare Google Civic Information with an official/commercial source against a representative test corpus.        | Current data has no uncovered-contest universe. National-only launch uses the existing researched-race catalog and makes no ballot-discovery claim. Local/judicial/measure coverage cannot launch without a qualified source.                                                                                                |
| Coverage matching       | Normalized identifiers in a Smarter.Vote contest catalog; exact provider-ID/GEOID matching first, reviewed aliases second; never title fuzzy matching in the request path                                | Reliable, explainable matching. Existing slugs remain public URLs. A future commercial feed maps through the same internal identity.                                                                                                                                                                                         |

### End-to-end flow

```text
Browser address field
  -> provider autocomplete with per-interaction session token
  -> user chooses suggestion (never submit free text silently)
  -> POST /lookup/resolve over TLS; no address in URL
  -> redact request before application/access/error telemetry
  -> normalize/geocode via Census (provider-coordinate fallback)
  -> resolve versioned geographic IDs
  -> query ElectionProvider adapters for elections/contests + official URLs
  -> normalize provider contests to internal ContestIdentity records
  -> exact-match published/draft catalog entries
  -> return coarse display geography, coverage groups, official links,
     confidence/warnings, provider/boundary versions, and expiry directly
  -> browser route /elections/near-you/ reads the result from memory/sessionStorage
  -> discard raw address and expire browser session data
```

### API contract

- `POST /lookup/resolve`: accepts a provider place token or structured address only as required, consent/context fields, and an idempotency/request token. Responds directly with the result payload and expiry. Rate-limit by rotating IP hash plus session, cap body size/timeouts, validate US-only inputs, and protect provider quotas.
- Do not add `GET /lookup/results/{opaque_id}` or a server result collection. Return the payload directly and store the minimum district/result data in expiring browser `sessionStorage` for refresh continuity.
- `GET /elections/catalog` or static `elections/catalog.json`: exposes non-personal contest identities/statuses for matching and directory use.
- `POST /events`: accepts allowlisted coarse product events, never address/place ID/lat-lon.

The public FastAPI service is the natural backend because it already runs on Cloud Run, uses Secret Manager/Firestore/rate limiting, and is the production API contract. Put lookup in a dedicated router/service module, not `main.py` or the local debug API. If geocoding latency/cost later needs isolation, migrate the adapter behind an internal Cloud Run service without changing the web contract.

### Quality, ambiguity, mobile, cost, and abuse

- Build a gold test corpus across all states: urban/rural, apartments, tribal lands, PO boxes, military addresses, border coordinates, renamed streets, at-large districts, split precincts, and unsupported territories. Store synthetic/public government addresses, not staff/user homes.
- Require confidence and provenance per geography. Never silently choose among ambiguous matches. PO boxes cannot resolve residence districts; explain and request a residential street address.
- On mobile, show 44px targets, stable keyboard behavior, `autocomplete="street-address"` only if provider guidance permits, a visible clear button, and no map requirement.
- Use provider session tokens correctly where the terminating request remains contractually compatible; request only billable fields needed; wait for at least four typed characters; debounce 350–500 ms; cancel stale requests; do not query again for an unchanged prefix; and use per-user/session throttles. Do not add negative caching of Google content.
- Start the Google pilot at **250 Autocomplete Requests/day**, **30 requests/minute for the project**, and **10 requests/minute per anonymous browser session**. These are conservative starting quotas, not capacity promises. At an estimated 3–6 requests per completed address, the daily quota supports roughly 40–80 completed lookups before falling back to the plain Census form.
- Set a **$10 monthly Google Maps Platform budget** with billing notifications at $1, $5, and $8 (plus 50%, 80%, and 100% where the billing console requires percentages). Google budgets are alerts rather than hard caps. The owner reviews the alerts and manually lowers the quota or disables the API if spending becomes unacceptable; do not build custom billing-shutdown automation. The ordinary error/quota-exceeded state displays the direct Census form so lookup does not fail completely.
- Restrict the browser/API key to the production and preview domains, Places API (New) only, and the minimum required endpoints. Use separate development/test credentials with near-zero quotas, disable unused Maps APIs, review billing weekly during the pilot, and alert on abnormal abandoned sessions or request-per-lookup ratios.
- Rate-limit suggestion proxy/resolve separately, reject automation patterns, bound downstream fan-out, use Cloud Armor/API gateway only if observed abuse justifies it, and provide a no-JavaScript/manual state browse fallback.

### Phase 0 provider gate

This gate is deferred until funding exists. Then score candidate stacks on match rate, correct congressional/state/local district rate, contest recall versus official sample ballots, p95 latency, cost per completed lookup, quotas/terms, accessibility, privacy/data retention, outage behavior, and identifier stability. Do not preselect Google Places + Census: approve that combination only after terms review. A commercial provider is likely necessary for dependable nationwide local/judicial/measure coverage.

Licensing and pricing research note (reviewed 2026-07-12; not legal advice): Google's current [Places API policies](https://developers.google.com/maps/documentation/places/web-service/policies) say applications need public Terms and Privacy policies, restrict prefetching/caching/storing Places content except place IDs, and require Google Maps attribution when results appear without a Google map. Google's [place ID guidance](https://developers.google.com/maps/documentation/places/web-service/place-id) confirms that place IDs may be retained and should be refreshed after 12 months. Those documents do not expressly approve sending a Places-selected formatted address to the Census service and using the Census-derived geography independently. Therefore “ephemeral” alone is not sufficient evidence of compatibility. Recheck the then-current agreement and obtain qualified review or written Google confirmation before implementation.

Google's current [core services pricing list](https://developers.google.com/maps/billing-and-pricing/pricing) gives Autocomplete Requests a 10,000-request monthly free usage cap and lists the next tier at $2.83 per 1,000 requests. Pricing and free caps can change, so the implementation must read the current pricing page before enabling billing. The 250/day quota intentionally remains below today's free cap in a typical 30-day month. Google's [session-pricing guidance](https://developers.google.com/maps/documentation/places/web-service/session-pricing) notes that abandoned/incomplete sessions revert to per-request billing; cost monitoring must therefore track API requests, not just completed address selections.

For category enablement, use these minimum audited recall gates against official sample ballots: federal contests **99%**, statewide and state-legislative contests **98%**, and any local/judicial/measure category **95% within each explicitly enabled geography**, with 100% correct district assignment for the gold corpus before public launch. These are product release thresholds, not claims of perfect real-world completeness. Until those gates are funded and met, only the existing national-election directory is enabled and no address-derived ballot claim is made.

## 9. Ballot incompleteness and disclosure strategy

Use “ballot” only in the action label users recognize. The result heading is **Elections near you**, followed by:

> This is not an official or complete sample ballot. Smarter.Vote shows elections we can identify and clearly marks where our research is unavailable. Local contests or ballot measures may be missing. Confirm your ballot with your state or local election authority.

Exact result labels:

1. **Research available** — the contest identity exactly matches published Smarter.Vote research.
2. **Election identified — research in progress** — a trusted election source identifies the contest, but no published research matches. Do not expose internal draft contents.
3. **Check official election information** — official resources exist, but Smarter.Vote cannot confidently match/describe the contest.
4. **We may not have identified every contest** — page-level warning whenever provider/category coverage is incomplete or unknown.

Group known contests by **Federal**, **Statewide**, **State legislature**, **Judicial**, **County**, **Municipal**, **Ballot measures**, and **Other** only when the provider explicitly classifies them. Omit unsupported empty categories rather than suggesting they were checked; separately show “Categories this source may not cover.” Display provider/source and retrieval time, geography confidence, election date, and an official-link block. Do not call a contest “missing” unless an authoritative comparison proves it; use “may not have identified.”

## 10. Sponsorship and partnership experience

### `/support/`

Sections: public-benefit statement; one-time/monthly selector; suggested unrestricted support amounts plus custom amount; uses of funds; campaign slot; independence summary; LLC/tax disclosure; privacy/public-recognition choice; FAQ; partner link.

Recommended legal/product copy:

> Smarter.Vote is an independent civic-technology project operated by Smarter.Vote LLC. We intend to pursue a nonprofit structure dedicated to clear, sourced, nonpartisan election information as a public resource. Payments to Smarter.Vote LLC are not currently tax-deductible charitable contributions. Sponsors and supporters have no control over our research, sources, ratings, forecasts, or conclusions.

Use “support” or “payment,” not “donation,” in transactional UI until counsel/accounting approves terminology. Do not promise a nonprofit conversion date.

Funding choices should be purpose-level: unrestricted; expand election/ballot coverage; accessibility and translation; data and infrastructure. Treat them as **nonbinding allocation preferences**, with clear copy that Smarter.Vote LLC retains discretion to use funds where most needed. Restricted funds create tracking, refund, contract, and unspent-balance obligations that are disproportionate at this stage. Accept a legally restricted grant/sponsorship only through a separately signed institutional agreement and bookkeeping process.

### `/partners/`

Serve five inquiry types: organizational sponsorship; newsroom/university/civic/nonprofit collaboration; grants/institutional funding; data/service in-kind partnership; data/API licensing/integration. Explain deliverables that are permissible (public acknowledgment, impact reporting, scoped engineering/data work, co-branded neutral resources subject to policy) and forbidden editorial influence. Collect name, work email, organization, inquiry type, message, approximate range, and consent; do not require an account. Initially deliver to `SmarterDotVote@gmail.com`; enable two-factor authentication, restrict access to the LLC owner, label messages by role/type, avoid forwarding to personal accounts, and delete declined/inactive inquiries 12 months after last contact.

### Coverage sponsorship

Allow funders to express interest in a state or category, but editorial/product staff apply published prioritization criteria: election proximity, public need, data availability, geographic equity, research cost, correction capacity, and conflicts. Contract language must say funding purchases capacity, not publication, conclusions, favorable treatment, or exclusivity. Label funded expansions at the program/collection level (“Coverage expansion supported by …”), not on individual candidate claims. If a single funder materially caused a race/region to be prioritized, disclose that fact on the collection and transparency register.

### Kickstarter-ready module

Model campaigns as optional content with title, goal, dates, status, external URL, progress source, and disclosure. `/support/` can replace its normal lead with a bounded campaign banner while keeping permanent one-time/monthly and partner paths. On expiry, archive campaign results and automatically remove urgent styling. Kickstarter remains an outbound campaign channel; do not mirror payments or invent progress without a supported API/manual audited update.

## 11. Editorial-independence and transparency policy

Publish the full policy before accepting institutional sponsorship. It must state that no supporter may influence candidate summaries, issue taxonomy/classification, source selection, confidence, forecasts/ratings, corrections, publication timing to suppress information, or conclusions; purchase favorable treatment; preview unpublished findings for approval; or receive candidate-level exclusivity.

Safeguards:

- Separate commercial discussions and editorial/research decisions; log prioritization decisions and conflicts.
- Use the same documented research, quality, source, and correction standards for sponsored and unsponsored work.
- Categorically reject money, paid promotion, or in-kind support from candidates, candidate committees, political parties/committees, PACs/Super PACs, ballot-measure committees, foreign governments/foreign political actors, and anonymous institutional sources whose beneficial funder cannot be identified. Also reject any agreement conditioned on coverage, timing, sources, ratings, conclusions, access to unpublished work, data suppression, or exclusivity. Apply enhanced review and public conflict disclosure to officeholders, lobbying firms, advocacy organizations, election/data vendors, and companies materially affected by a covered issue; decline when independence cannot be credibly protected. Individual employees/supporters are not automatically prohibited solely because of an employer, but contribution patterns and known conflicts may trigger review. Have counsel refine these rules before institutional funds are accepted.
- No sponsor-branded candidate cards, issue rows, forecasts, or calls to vote.
- Publish sponsor legal name, relationship type, supported program/geography, term, and amount band (recommended bands: under $5k, $5k–$24,999, $25k–$99,999, $100k+) unless safety/law requires a documented exception. Individual supporters are private by default and public only by explicit opt-in.
- Publish conflict disclosures promptly and an annual transparency report covering revenue by category/band, major funders, in-kind support, sponsored priorities, corrections, coverage metrics, and policy exceptions.
- Smarter.Vote LLC holds final editorial authority. The public contact for corrections and conflicts is initially `SmarterDotVote@gmail.com`. As soon as another qualified reviewer joins, name the responsible individual(s), require the LLC owner to document personal conflicts, and add recusal/escalation rules; an organization name alone is accountability, but not a substitute for a named human in the mature policy.

## 12. Payment architecture

### Recommendation

Use Stripe-hosted Checkout Sessions created by `services/races-api` for one-time payments and recurring monthly subscriptions. Use Stripe Customer Portal for self-service subscription/payment-method changes and Stripe Invoicing for negotiated institutional contracts. Payment Links are useful only as an emergency/campaign fallback because they weaken first-party attribution, dynamic consent metadata, and lifecycle control. Embedded checkout adds frontend/security/accessibility surface without a current benefit.

### Flow and records

```text
/support selection
  -> POST /payments/checkout-sessions (amount/product allowlist + idempotency)
  -> Stripe-hosted Checkout
  -> Stripe webhook on Cloud Run verifies raw-body signature
  -> idempotent event ledger + supporter/subscription/payment projection in Firestore
  -> /support/thanks/?session_id=... verifies server-side status
  -> Stripe receipt; optional separate acknowledgment email
```

Use Stripe Price IDs configured server-side; never accept arbitrary recurring price IDs or trust client success redirects. Allow a bounded custom one-time amount in USD with server validation. Webhook handlers acknowledge quickly and process idempotently; tolerate duplicates/out-of-order events. Handle `checkout.session.completed`, async success/failure, invoice paid/payment failed, subscription changes/deletion, disputes, refunds, and chargebacks. Reconcile Stripe to Firestore/accounting on a schedule; Stripe is financial source of truth, Firestore is the product projection.

Suggested collections: `supporters` (Stripe customer reference, contact/recognition preferences), `support_payments` (Stripe IDs, gross/refund/status/currency/purpose, timestamps), `support_subscriptions`, and `stripe_events` (event ID/type/processed status; minimal payload or encrypted short retention). Never store card/bank data. Restrict IAM and admin views by least privilege and do not reuse Auth0 admin identity as a public customer account.

Business identity, statement descriptor, receipt email, refund policy/contact, terms, privacy link, and LLC/non-deductibility disclosure must be configured consistently in Stripe and the site. Smarter.Vote LLC is the refund authority and `SmarterDotVote@gmail.com` is the initial contact. Recommended consumer policy: honor refund requests within 30 calendar days of a one-time payment when funds have not been contractually committed or irreversibly spent; cancel recurring support prospectively at any time and consider its latest charge under the same 30-day rule; promptly resolve duplicate/unauthorized payments; and make institutional invoices follow their signed agreement. This is product guidance requiring counsel/accountant review. Stripe Tax is not assumed to solve income, sales-tax, campaign, or charitable rules. Accounts are not required. Public name recognition is a separate unchecked opt-in; amount is private by default.

Do not activate live payments until the LLC has its approved legal name/EIN and bank/Stripe verification, a non-home public mailing address or registered-agent/business address approved for public use, bookkeeping, Terms, Privacy Policy, refund policy, statement descriptor, and counsel/accountant review. Do not publish a home address. Before readiness, `/support/` may explain the mission and link the partnership email, but must not collect payment details.

Secrets: `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in Secret Manager, public publishable key only if later needed, distinct test/live keys and webhook endpoints, restricted keys where feasible, rotation/runbook/alerts. Log Stripe object IDs and status, not full webhook payloads or customer PII. Test mobile, keyboard/screen reader flow, 3DS, cancellation, failure, retry, refund, subscription cancellation, duplicate events, and webhook replay.

## 13. Privacy and security

- Default: do not store full addresses. Raw input may reach the backend only if Census/provider requirements demand it; it exists in process memory for one request and is redacted before framework, Cloud Run, analytics, and error telemetry.
- The lowest-cost future pilot should submit a user-entered address directly to Census and discard it after resolution. Do not send Google Places-derived address content to Census unless qualified review or written Google confirmation approves that exact workflow. If Places is later used, provide required Google attribution and public Terms/Privacy links, retain only place IDs where allowed, and do not cache Places content.
- Never put address, place ID, coordinates, precinct, lookup token, email, or payment status in page URLs, referrers, analytics properties, DOM metadata, support tickets, or error messages.
- Persist only coarse district identifiers, provider/boundary versions, coverage outcome counts, and rounded/coarsened geography needed for anonymous product metrics. Precinct or exact coordinates are sensitive and should remain ephemeral.
- Browser state: memory first; `sessionStorage` only for district/result payload needed for refresh, cleared on tab close/expiry. No localStorage or service-worker caching. Set personalized API responses `Cache-Control: no-store`.
- Create endpoint-specific log filters/middleware before lookup. Current API analytics hashes IPs but still should exclude lookup/payment paths or record only allowlisted operational fields. Rotate hash salt and document retention.
- Cloudflare analytics and consent/privacy copy must disclose processor use. Disable query-string collection where possible and confirm no replay/session-recording tool captures forms.
- Retention proposal: lookup request body and server result 0 days; browser session result 30 minutes maximum; coarse aggregate events 13 months maximum; inquiry PII 12 months after last contact unless an active relationship; payment/accounting records per accountant/legal requirements; webhook payloads minimized and short-lived while event IDs/status remain for idempotency.
- Add deletion/contact procedures, data inventory, processor/subprocessor list, incident response, secret rotation, SSRF/URL validation, dependency scanning, webhook signature verification, CORS review, and abuse/cost alerts.

Privacy copy by the field: “We use your address only to identify election districts. We do not save it or use it for political profiling.” This promise must be validated against provider and infrastructure behavior before publication.

## 14. SEO and social sharing

- Homepage title: **Smarter.Vote — Sourced candidate research for elections near you**. Description: **Find elections relevant to your address and compare clear, sourced, nonpartisan candidate research. Coverage is expanding and may be incomplete.**
- `/support/`: title **Support Smarter.Vote | Expand sourced election coverage**; description must mention Smarter.Vote LLC and avoid charitable/tax language.
- `/partners/`: title **Partner with Smarter.Vote | Civic information partnerships**.
- Keep race/candidate canonical routes and update “unbiased AI analysis” metadata to sourced/nonpartisan language. Add per-race OG data using existing race title/date/candidates where stable.
- Personalized result route: `<meta name="robots" content="noindex,nofollow">`, canonical `/elections/`, no address-derived server-rendered title, and no sitemap entry. Avoid share buttons; share stable race URLs instead.
- Add new static routes to `generate-sitemap.mjs`; never add thank-you, admin, lookup result, or query-derived URLs. Update `robots.txt` defensively, understanding `noindex` and data design—not robots alone—provide protection.
- Use `Organization`/`WebSite` JSON-LD only with verifiable Smarter.Vote LLC identity/contact/logo fields. Use `FAQPage` only for visible support FAQs and only if current search-engine policy permits. Do not use `DonateAction` or nonprofit schema that misstates status. Election-specific structured data should be deferred unless a well-supported schema maps accurately.
- Create neutral 1200×630 homepage/support/partners social cards from the existing brand asset process; no partisan split imagery or unsupported metrics.

## 15. Accessibility

- Implement autocomplete as a WAI-ARIA combobox/listbox with a persistent `<label>`, instructions, `aria-expanded`, `aria-controls`, `aria-activedescendant`, Escape/arrow/Enter behavior, and status announcements for result counts. Prefer a provider library only if its rendered UI passes this contract.
- Do not use placeholder as label. Announce validation, provider failure, loading, ambiguous selection, coverage summary, and result changes with appropriately scoped live regions.
- On submit, move focus to the result heading; on inline errors, focus/associate an error summary. Preserve entered text when retrying unless privacy requires clearing, and provide a clear action.
- Provide skeletons plus text, not spinner-only states. Do not encode availability/party/confidence in color alone.
- Maintain WCAG 2.2 AA contrast, visible focus, 44×44 touch targets, semantic headings/landmarks, logical DOM order, zoom/reflow at 320 CSS px, reduced motion, and dark-mode parity.
- Ensure Stripe-hosted checkout, inquiry forms, tables, source links, disclosure accordions, and campaign progress have accessible names/alternatives. Test with keyboard, NVDA/Chrome, VoiceOver/Safari, and mobile screen readers.

## 16. Analytics and success metrics

Define an allowlisted first-party product-event schema: `hero_lookup_started`, `suggestion_selected`, `lookup_submitted`, `lookup_succeeded`, `lookup_partial`, `lookup_failed` (reason enum), `official_resource_opened`, `research_race_opened`, `directory_opened`, `support_checkout_started`, `support_checkout_returned`, and `partner_inquiry_submitted`. Include page, experiment/config version, coarse device, coverage counts, provider outcome enum, and latency bucket. Exclude address, place ID, lat/lon, district combination when re-identification risk is high, race selection history, free text, email, Stripe customer/session ID, and raw referrer query.

Primary metrics:

- Lookup completion rate and valid-suggestion-to-result rate.
- Exact district/contest match rate from audited gold corpus.
- Percentage of successful lookups with ≥1 research match; distributions of researched/known-unresearched/unknown-category results.
- Official-resource click-through and race-research click-through.
- p50/p95 latency, provider failures, quota use, cost per completed lookup.
- Correction submissions and time to resolution; research freshness/coverage metrics.
- Checkout start-to-paid conversion, monthly recurring revenue, retention/churn, refunds/failures, and partner qualified inquiries—viewed only in aggregate with role restrictions.

Do not optimize for time-on-site or partisan engagement. Establish baseline, target, owner, and review cadence in Phase 0. Popular/featured election analytics require a privacy threshold (for example minimum aggregate count) before public ranking.

## 17. Data model and API changes

Keep research `RaceJSON` separate from election discovery. Proposed models:

- `ContestIdentity`: internal ID; election ID; provider IDs; office type/level; state FIPS; jurisdiction type/ID/name; chamber; district label/number/GEOID; election date/stage; partisan flag; official URL; source/provenance; status.
- `ElectionIdentity`: internal/provider IDs; name/date/type; registration/official/sample-ballot links; source timestamp.
- `GeographyResolution`: state/county/congressional/state-legislative/municipal/special identifiers, confidence, boundary vintage, source—ephemeral in lookup responses.
- `CoverageMatch`: contest internal ID, race slug, state (`published`, `research_in_progress`, `not_researched`, `unmatched`), match method/confidence, reviewed override.
- `CoverageProfile`: provider/category/geography coverage declarations and caveats used to generate honest page warnings.
- `FeaturedRaceConfig` and `SiteMetricsSnapshot`: reviewed IDs and reproducible aggregate counts with timestamps.
- Payment/support models described in Section 12 and campaign/sponsor disclosure records described in Sections 10–11.

Add normalized identity fields to shared race metadata and TypeScript mirrors only after backfill rules are proven. Preserve existing race slug/URLs. Populate the Firestore contest catalog through a versioned import/reconciliation job; publish a sanitized static index for frontend use if useful. Every provider record must retain provenance and `observed_at`; never overwrite reviewed mappings silently. Provide an admin review queue for ambiguous/unmatched contests and a coverage dashboard before public lookup.

## 18. Frontend component plan

Create reusable components rather than expanding `+page.svelte`:

- `AddressLookupForm.svelte`: form orchestration and disclosures.
- `AddressAutocomplete.svelte`: provider-neutral accessible combobox.
- `CoverageDisclosure.svelte`: canonical incomplete-coverage/privacy text.
- `LookupResults.svelte`, `ElectionResultGroup.svelte`, `CoverageStatusBadge.svelte`, `OfficialResources.svelte`.
- `ResearchPreview.svelte`: compact composition using real `IssueTable`/`SourceLink` concepts.
- `HowItWorks.svelte`, `TrustPrinciples.svelte`, `ImpactMetrics.svelte`, `FeaturedElections.svelte`.
- `SupportCheckoutForm.svelte`, `LlcDisclosure.svelte`, `CampaignBanner.svelte`, `PartnerInquiryForm.svelte`, `SponsorDisclosureList.svelte`.
- Shared `SiteHeader.svelte`, `SiteFooter.svelte`, `PageMeta.svelte`, `Alert/StatusMessage.svelte`, and form primitives to reduce layout duplication.

Extract directory behavior from the current homepage into `ElectionDirectory.svelte` and centralize race filters/office categorization in utilities. Add compact variants to existing cards only when semantics remain the same. Avoid importing admin services into public routes.

## 19. Backend and infrastructure plan

- Add dedicated FastAPI routers/services for lookup, election catalog, public events, payments/webhooks, and partner inquiries. Keep adapters behind protocols with timeouts, bounded retries, ordinary failure fallbacks, and test fakes; a custom provider kill-switch system is unnecessary.
- Add Firestore collections/indexes/TTL policies for contest catalog, short-lived lookup results if enabled, provider cache, mapping review, support projections, webhook idempotency, inquiries, sponsor disclosures, and aggregate product events.
- Add Secret Manager resources/IAM for autocomplete/geocoder/election provider, Stripe, webhook, and inquiry delivery credentials. Keep browser-visible provider keys domain/API restricted; prefer server-issued tokens/proxy where provider design supports it.
- Add Terraform variables, Cloud Run environment bindings, API enablement if needed, budget/quota monitoring, alerting, Firestore indexes/TTL, and least-privilege service-account roles. Revisit Cloud Run max instances/concurrency after provider and webhook load tests.
- Exclude sensitive endpoints from existing analytics middleware and implement structured redaction before route launch. Configure CORS narrowly and `no-store` headers.
- Add provider import/reconciliation as an explicit admin/job workflow; do not make user lookup trigger expensive research runs or publish data.
- Maintain static GCS race reads. Personalized lookup/payment APIs are dynamic and isolated from public race cache paths.

## 20. Error, loading, empty, and partial-data states

| State                     | User-facing treatment                                                            | Recovery                                                   |
| ------------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Suggestions loading       | “Finding addresses…” announced without blocking typing                           | Cancel stale requests                                      |
| No suggestion             | “We couldn’t find that address. Include street number, street, city, and state.” | Retry; browse state                                        |
| Ambiguous                 | “Choose the address that matches where you live.”                                | Retain choices; no silent selection                        |
| PO box/non-residential    | Explain that residence districts require a street address                        | Browse official/state resources                            |
| Autocomplete outage       | “Address suggestions are temporarily unavailable.”                               | Retry/manual directory; never submit unresolved string     |
| Geocoder/boundary failure | “We found the address but couldn’t determine all districts.”                     | Partial results clearly flagged; official link             |
| Election provider failure | “We couldn’t check election listings right now.”                                 | Show no stale completeness claim; retry/official resources |
| No research match         | “We haven’t published research matching these districts yet.”                    | Known contests/official resources/support link             |
| Partial categories        | Name categories/source limitations                                               | Official authority link                                    |
| Stale research            | Show last update and “May be outdated”                                           | Sources/correction link                                    |
| Preview/metrics failure   | Omit section or deterministic fallback                                           | Never show fabricated zero/sample metrics                  |
| Checkout canceled         | Neutral return with selection retained                                           | Resume checkout                                            |
| Payment pending/failed    | Verify server-side; no false success                                             | Stripe retry/support contact                               |
| Duplicate webhook         | No user impact; idempotent acknowledgment                                        | Operational log/metric only                                |
| Inquiry failure           | Preserve nonsensitive fields locally in memory                                   | Retry/copy contact email                                   |

## 21. Testing strategy

- Unit tests: normalization/matching, provider adapters, coverage labeling, redaction, rate-limit keys, Stripe signature/idempotency/state transitions, metrics, copy/route utilities, and component state/accessibility behavior.
- Contract tests with recorded sanitized fixtures for every provider and Stripe test events; reject schema drift and missing provenance. Network remains mocked in normal tests.
- Integration tests against local FastAPI/Firestore emulator or isolated test project for TTL, mappings, webhook replay/out-of-order events, and no-store/log redaction.
- Frontend tests for keyboard combobox, focus/live regions, partial states, URL privacy, support disclosure/consent, and directory regression.
- Playwright end-to-end tests at mobile/desktop widths for lookup happy/ambiguous/failure paths, result-to-race navigation, checkout test mode, cancellation, and partner inquiry.
- Data-quality tests compare the gold address corpus with official district/ballot sources and produce category/state recall reports. Human review is required before raising coverage claims.
- Security/privacy tests assert sensitive strings never reach logs, analytics events, URLs, HTML metadata, session persistence after expiry, or error reporting; test SSRF, injection, forged webhooks, replay, arbitrary prices, quota abuse, and CORS.
- Accessibility: automated axe plus keyboard and screen-reader manual matrix. Visual regression for light/dark, reduced motion, contrast, long names, zoom, and sparse/dense results.
- Run narrow suites per phase and the repository CI gates before merge; validate production-like Cloudflare/GCS/API behavior in staging because local fallback data can conceal failures.

## 22. Rollout and migration strategy

1. Inventory/legal/provider validation; freeze public terminology and baseline metrics.
2. Ship trust/methodology/privacy/corrections/funding pages and the new homepage shell while the existing directory remains available at both `/` and hidden `/elections/` during migration.
3. Canonically move the directory to `/elections/`; preserve root search query behavior with redirects/mapping where practical and update sitemap/navigation.
4. Build catalog/import/admin matching tools and run silently. Compare results against official ballots; no public address CTA.
5. Release lookup to staff, then a small geography allowlist, then wider traffic. Show service coverage by geography and retain the directory/Census fallback. Google can be disabled manually in Cloud Console or deployment configuration if necessary; do not build a bespoke runtime kill switch.
6. Launch `/support/` and `/partners/` content/inquiries before payments. Remove GitHub Sponsors from primary organization-level CTAs immediately; a quiet **Support the developer** link to the existing personal GitHub Sponsors page may remain in the About page's maintainer section and must be clearly distinguished from payments to Smarter.Vote LLC.
7. Enable Stripe for a limited live cohort/amount range only after LLC/payment readiness, reconcile first transactions, then expand recurring support. Existing GitHub Sponsors subscriptions are neither imported nor represented as LLC support; no migration or duplicate-charge outreach is needed.
8. Review after one election cycle; expand providers/local categories based on audited recall, not marketing deadlines.

Do not A/B test whether users see the coverage warning or privacy disclosure. Experiments may test layout/copy only while keeping legal meaning and prominence fixed.

## 23. Risks and mitigations

| Risk                                            | Mitigation                                                                                                                     |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Users infer a complete/official ballot          | Result terminology, persistent disclosure, official links, audited provider/category coverage, no “complete” claim             |
| Incorrect districts or contest matching         | Census/boundary provenance, exact IDs, confidence, gold corpus, review overrides, no ZIP inference/fuzzy runtime match         |
| Local-election gaps                             | Provider pilot, coverage profiles, commercial migration path, explicit category caveats                                        |
| Address leakage                                 | POST only, redaction before middleware, ephemeral processing, no-store/session expiry, privacy tests                           |
| Provider cost/outage/lock-in                    | Adapter interfaces, billing alerts, configured quotas, bounded retries, cached non-PII catalog, and Census/directory fallbacks |
| Static frontend conflicts with dynamic features | Keep research static; isolate lookup/payment in FastAPI; feature flags and resilient shells                                    |
| Sponsor conflict or public distrust             | Binding policy, prohibited-funder rules, amount bands, disclosure register, recusal, annual report                             |
| LLC/tax/payment misstatement                    | Counsel/accountant approval, exact disclosure, Stripe receipts, no “tax deductible”/charity claims                             |
| Webhook/accounting drift                        | Stripe source of truth, idempotent ledger, reconciliation, alerts/runbook                                                      |
| Metrics become misleading                       | Reproducible definitions, timestamps, production source, omit unavailable metrics                                              |
| Current data fields cannot map geography        | Normalized identity backfill and admin review before lookup launch                                                             |
| Monolithic UI regresses                         | Extract components/utilities and preserve directory tests before redesign                                                      |

## 24. Open questions

### Decisions now resolved

- **Provider/launch scope:** no funded ballot provider exists; initial coverage is national elections only. Local/judicial/measure lookup is deferred. Future recall gates are 99% federal, 98% statewide/legislative, and 95% for each explicitly enabled local category/geography, with 100% district accuracy in the gold corpus.
- **Places/Census:** compatibility is not established. Current Google policy allows place-ID storage but restricts other Places-content storage and requires attribution/Terms/Privacy. Do not build the cross-provider flow without qualified review or written confirmation; direct Census entry is the low-cost pilot.
- **Authority/contact:** Smarter.Vote LLC is accountable; `SmarterDotVote@gmail.com` initially receives corrections, privacy, refund, and partnership messages. Named human roles remain a maturity goal.
- **Funder policy:** categorically prohibited and enhanced-review classes are recommended in Section 11; counsel must refine them before institutional acceptance.
- **Allocations:** individual supporter choices are nonbinding preferences; only separately contracted institutional funds may be restricted.
- **Payment readiness:** live payments wait for LLC/EIN/bank/Stripe verification, non-home public address, bookkeeping, approved legal policies, and professional review. A provisional 30-day refund recommendation is in Section 12.
- **Homepage preview/metrics:** use deterministic eligibility rules and reproducible national-coverage metrics described in Section 7; Smarter.Vote LLC signs off initially.
- **Result persistence:** browser memory and expiring `sessionStorage`; no server-side result record.
- **Inbox:** Gmail initially, owner-only with 2FA, labels, no personal forwarding, and 12-month deletion for inactive inquiries.
- **GitHub Sponsors:** no migration; retain only an optional personal **Support the developer** About-page link, clearly separate from LLC support.

### Remaining gates

1. Which funded election provider eventually passes the gold corpus and contractual review?
2. Does qualified review or written Google confirmation permit the exact Places-to-Census flow, including ephemeral transfer and derived district use?
3. What non-home address may legally and safely appear in the LLC's public/payment documents?
4. What final Terms, Privacy Policy, refund policy, funder rules, amount bands, and sponsor exceptions do counsel/accounting approve?
5. Who becomes the first named human reviewer or backup authority when the organization grows beyond its owner?

## 25. Implementation phases

### Phase 0: product, legal, provider, and data validation

**Purpose:** Remove the largest truth, privacy, identity, and business uncertainties before building public promises.
**Dependencies:** Owner, counsel/accountant, provider test credentials, official reference ballots.
**Tasks:** Define copy/policies/metrics; build gold corpus and provider spike; audit Places terms; define contest identity and coverage taxonomy; measure production fields; select preview race; define Stripe business/refund/accounting setup; threat model and data inventory; establish feature flags and success gates.
**Likely systems:** Design/product records, provider sandboxes, `shared/models.py` spike only after approval, no public launch.
**Tests:** Provider accuracy/cost/latency report, privacy data-flow review, Stripe test-mode proof, accessibility prototype.
**Risks:** Representative corpus bias, provider availability, unresolved legal status.
**Complete for the national-only launch when:** The owner approves terminology/policies, deployed national data supports the preview/metrics definitions, and privacy/payment deferrals are documented. **Complete for future lookup when:** a funded provider stack and launch geography pass thresholds and the normalized identity/backfill plan has sampled proof.

### Phase 1: homepage, directory, and trust foundation

**Purpose:** Improve comprehension and credibility without waiting for lookup.
**Dependencies:** Approved copy, preview selection, metric definitions.
**Tasks:** Componentize layout; create `/elections/`; redesign root sections; add methodology/corrections/privacy/terms/funding policy routes; revise About/navigation/footer/metadata; implement real preview, metrics snapshot, recently updated cards; retain visible “lookup testing” state until enabled.
**Files/systems:** Svelte routes/components/styles, sitemap/robots, GCS-derived public data build.
**Tests:** Component/accessibility/visual tests, directory parity, static build/prerender/link/SEO tests.
**Risks:** SEO regressions, duplicate route logic, stale demo/metrics.
**Complete when:** First-time usability review passes; root no longer renders the full directory; all trust claims link to policies; no fabricated data; `/elections/` preserves discovery behavior.

### Phase 2: election catalog and address/district resolution

**Purpose:** Build reliable lookup foundations without claiming ballot coverage.
**Dependencies:** Phase 0 providers/identity; API secrets/IAM/budgets.
**Tasks:** Add contest/election catalog import, normalized race fields/backfill, mapping review tools; implement autocomplete and `/lookup/resolve`; Census/boundary adapters; redaction/rate limits/cache/quotas; internal result UI; feature flags.
**Files/systems:** Shared schemas/types, FastAPI routers/services/tests, Firestore/indexes/TTL, Secret Manager/Terraform, frontend lookup components.
**Tests:** Gold corpus, adapter contracts, abuse/privacy/logging, accessible combobox, staging load/cost.
**Risks:** Identifier mismatch, address leakage, provider gaps/cost.
**Complete when:** Enabled geographies meet district-accuracy thresholds; sensitive-data tests pass; ambiguous/failed cases are recoverable; catalog mappings are reviewable and versioned.

### Phase 3: ballot-style results and coverage states

**Purpose:** Connect resolved geography to researched and known-unresearched contests honestly.
**Dependencies:** Phase 2 catalog/lookup; official-resource coverage.
**Tasks:** Implement exact matching, coverage profiles, result grouping/labels/official resources, short-lived session behavior, noindex metadata, partial/stale states, correction links, aggregate events; conduct external content/UX review.
**Files/systems:** Lookup result route/components, matching service/models, catalog/admin review, analytics aggregation.
**Tests:** Official-ballot comparisons, no-address URL/index tests, partial/outage E2E, screen reader/focus tests.
**Risks:** Completeness inference, provider omissions, stale mappings.
**Complete when:** Every result declares source/coverage limits; no zero-result says “no elections”; recall report meets enabled-category targets; fallback, quota handling, alerts, and monitoring work.

### Phase 4: support and partnership content

**Purpose:** Replace developer-oriented sponsorship UX with professional, accurate paths before taking new payments.
**Dependencies:** LLC/legal copy, policies, inquiry owner/processor.
**Tasks:** Build `/support/`, `/partners/`, campaign module, sponsor register/policy, inquiry and correction forms; update About/race missing-data/nav/footer links; keep payments disabled or waitlist CTA.
**Files/systems:** Static routes/components, inquiry API/notification/storage, metadata/social cards/sitemap.
**Tests:** Form validation/spam/privacy/accessibility, policy-link and metadata tests.
**Risks:** Legal ambiguity, spam, implied quid pro quo.
**Complete when:** All audiences have clear next steps; LLC/non-deductibility and independence disclosures are prominent; GitHub is no longer required for public support/corrections.

### Phase 5: payments and recurring support

**Purpose:** Accept/reconcile secure one-time and monthly support.
**Dependencies:** Stripe live account/business verification, refund/accounting process, Phase 4 policies.
**Tasks:** Checkout/session/portal endpoints; webhook ledger/projections; Firestore/Terraform/secrets; test/live configuration; receipts/thanks/status; refund/failure/dispute operations; restricted admin reporting and reconciliation.
**Files/systems:** FastAPI payment router/service/models/tests, frontend checkout/thanks, Firestore, Secret Manager, Terraform, runbooks.
**Tests:** Stripe CLI/test clocks/cards, signatures/replay/order, arbitrary amount/price rejection, 3DS/mobile/a11y, refund/subscription/reconciliation.
**Risks:** Financial drift, secret exposure, false success, tax/receipt errors.
**Complete when:** First controlled live payments reconcile end-to-end; failures/refunds/cancellations work; alerts/runbooks/owners exist; GitHub Sponsors is removed as primary CTA.

### Phase 6: launch hardening and measured expansion

**Purpose:** Validate reliability and expand only where evidence supports it.
**Dependencies:** Prior phases, production monitoring, support capacity.
**Tasks:** Performance/load/security/a11y audit; analytics dashboards; privacy/retention deletion jobs; provider cost alerts; SEO validation; incident exercises; phased geography rollout; transparency-report process; post-election review.
**Files/systems:** CI/E2E, monitoring, dashboards, retention jobs, operational docs.
**Tests:** Full CI, synthetic probes, disaster/provider outage, webhook reconciliation, manual screen-reader/security review.
**Risks:** Election traffic spikes, third-party outage, operational overload.
**Complete when:** SLOs, budgets, privacy retention, escalation, and rollback are exercised; expansion decisions use audited quality and user outcomes.

## 26. File-by-file anticipated changes

The names below are implementation targets, not changes made by this plan.

### Confirmed existing files likely to change

| File                                                                                                                          | Expected responsibility                                                                                                             |
| ----------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `web/src/routes/+page.svelte`                                                                                                 | Replace directory-first root with composed homepage sections and lookup entry.                                                      |
| `web/src/routes/+page.ts`                                                                                                     | Load preview, featured races, metrics/config; fail safely.                                                                          |
| `web/src/routes/+layout.svelte`                                                                                               | Replace duplicated nav/footer/search markup with shared components; add routes and revised support links; review analytics loading. |
| `web/src/routes/+layout.ts`                                                                                                   | Avoid loading all summaries globally if new header no longer needs them; keep deliberate shared data.                               |
| `web/src/routes/about/+page.svelte`                                                                                           | Correct LLC/project language, remove “unbiased”/AI guarantees and embedded GitHub Sponsors, link policies.                          |
| `web/src/routes/about/+page.ts`                                                                                               | Metadata/prerender support if still needed.                                                                                         |
| `web/src/routes/races/[slug]/+page.svelte`                                                                                    | Replace GitHub sponsorship/missing-coverage CTAs; add correction/funding disclosure links and consistent staleness labels.          |
| `web/src/lib/components/RaceCard.svelte`                                                                                      | Compact/featured/status variant if semantics remain shared.                                                                         |
| `web/src/lib/components/NoDataFallback.svelte`                                                                                | First-party correction/coverage language; official/support paths.                                                                   |
| `web/src/lib/components/IssueTable.svelte`, `ConfidenceIndicator.svelte`, `SourceLink.svelte`                                 | Accessible compact presentation and clearer confidence/source language.                                                             |
| `web/src/lib/api.ts`, `config/api.ts`                                                                                         | Typed lookup, event, inquiry, and payment calls; retain static race reads.                                                          |
| `web/src/lib/types.ts`                                                                                                        | Mirror approved shared identity/coverage/API models.                                                                                |
| `web/src/app.css`, `web/tailwind.config.js`                                                                                   | Semantic coverage/support/form tokens and reduced-motion/focus primitives.                                                          |
| `web/src/app.html`                                                                                                            | Global metadata/security hints only if required.                                                                                    |
| `web/scripts/generate-sitemap.mjs`, `web/static/robots.txt`, `web/static/sitemap.xml`                                         | Add public routes and exclude personalized/transaction routes. Generated sitemap remains generated.                                 |
| `web/static/og-image.png` and brand export assets/scripts                                                                     | Updated neutral social cards through the established asset workflow.                                                                |
| `web/package.json`/lockfile                                                                                                   | Only if the selected accessible provider SDK/testing tool is justified; prefer web APIs/current stack.                              |
| `shared/models.py`, `shared/race_catalog.py`                                                                                  | Add normalized election/contest identity and coverage fields; shape summaries/backfills.                                            |
| `services/races-api/main.py`                                                                                                  | Register new routers/middleware exclusions; do not place business logic here.                                                       |
| `services/races-api/analytics_middleware.py`, `analytics_store.py`                                                            | Exclude/redact sensitive paths and support allowlisted aggregate product events.                                                    |
| `services/races-api/request_models.py`, `schemas.py`                                                                          | Request/response validation for new public contracts where shared models are not appropriate.                                       |
| `services/races-api/requirements.txt`, `Dockerfile`                                                                           | Stripe/provider packages/modules only when needed.                                                                                  |
| `services/races-api/test_races_api.py`                                                                                        | Public route, rate-limit, redaction, failure, and cache header contracts.                                                           |
| `infra/races-api.tf`, `secrets.tf`, `variables.tf`, `firestore-indexes.tf`, `firestore-ttl.tf`, `monitoring.tf`, `outputs.tf` | Provider/Stripe secrets and IAM, env, collections/indexes/TTL, budgets/alerts, outputs.                                             |
| `infra/secrets.tfvars.example`                                                                                                | Empty documented variable placeholders; never real secrets.                                                                         |
| `.github/workflows/cloudflare-deploy.yaml`, `terraform-deploy.yaml`, `ci.yaml`                                                | Public config, secret synchronization, E2E/data-contract gates if required.                                                         |
| `docs/architecture.md`, `docs/deployment-guide.md`, `docs/local-development.md`, `docs/README.md`, `infra/README.md`          | Update canonical runtime/deployment/dev/document maps in the implementation changes.                                                |

### Proposed new files

| File                                                                                                                                                                                                                                | Expected responsibility                                                                                                                                             |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `web/src/routes/elections/+page.svelte` and `+page.ts`                                                                                                                                                                              | Full directory moved from homepage.                                                                                                                                 |
| `web/src/routes/elections/near-you/+page.svelte` and `+page.ts`                                                                                                                                                                     | Noindex personalized result shell.                                                                                                                                  |
| `web/src/routes/methodology/+page.svelte`, `corrections/+page.svelte`, `privacy/+page.svelte`, `terms/+page.svelte`                                                                                                                 | Durable trust/legal/correction content.                                                                                                                             |
| `web/src/routes/support/+page.svelte`, `support/thanks/+page.svelte`, `partners/+page.svelte`, `funding-and-editorial-independence/+page.svelte`                                                                                    | Support, payment return, institutional, and funding policy experiences.                                                                                             |
| `web/src/lib/components/site/SiteHeader.svelte`, `SiteFooter.svelte`                                                                                                                                                                | Shared shell.                                                                                                                                                       |
| `web/src/lib/components/lookup/AddressAutocomplete.svelte`, `AddressLookupForm.svelte`, `LookupResults.svelte`, `ElectionResultGroup.svelte`, `CoverageStatusBadge.svelte`, `OfficialResources.svelte`, `CoverageDisclosure.svelte` | Provider-neutral accessible lookup/result UI.                                                                                                                       |
| `web/src/lib/components/home/ResearchPreview.svelte`, `HowItWorks.svelte`, `TrustPrinciples.svelte`, `ImpactMetrics.svelte`, `FeaturedElections.svelte`                                                                             | Composable homepage sections.                                                                                                                                       |
| `web/src/lib/components/support/SupportCheckoutForm.svelte`, `LlcDisclosure.svelte`, `CampaignBanner.svelte`, `PartnerInquiryForm.svelte`, `SponsorDisclosureList.svelte`                                                           | Support/partnership components.                                                                                                                                     |
| `web/src/lib/components/ElectionDirectory.svelte` and `web/src/lib/utils/raceFilters.ts`                                                                                                                                            | Extract current directory behavior and shared filtering.                                                                                                            |
| `web/src/lib/services/lookupService.ts`, `supportService.ts`, `productEvents.ts`                                                                                                                                                    | Typed public API boundaries with privacy allowlists.                                                                                                                |
| `services/races-api/routers/lookup.py`, `payments.py`, `public_events.py`, `partnerships.py`                                                                                                                                        | Thin FastAPI route layers.                                                                                                                                          |
| `services/races-api/lookup_service.py`, `contest_matcher.py`, `election_catalog.py`                                                                                                                                                 | Resolution orchestration, exact matching, import/reconciliation.                                                                                                    |
| `services/races-api/providers/base.py`, `places.py`, `census.py`, and selected election-provider module                                                                                                                             | Replaceable provider adapters.                                                                                                                                      |
| `services/races-api/payment_service.py`                                                                                                                                                                                             | Stripe session/portal/webhook and projections.                                                                                                                      |
| `services/races-api/privacy.py`                                                                                                                                                                                                     | Shared sensitive-field redaction/no-store/logging helpers.                                                                                                          |
| `services/races-api/test_lookup.py`, `test_contest_matcher.py`, `test_payments.py`, `test_privacy.py`, `test_partnerships.py`                                                                                                       | Focused backend tests.                                                                                                                                              |
| `web/src/lib/components/lookup/*.test.ts`, `support/*.test.ts`, `web/tests/*.spec.ts`                                                                                                                                               | Component and E2E coverage; exact placement follows current test convention/Playwright setup.                                                                       |
| `docs/funding-and-editorial-independence.md`, `docs/address-lookup-privacy-runbook.md`, `docs/payments-operations.md`                                                                                                               | Canonical policy source and internal privacy/payment operations; public pages may render approved content from dedicated sources depending on content architecture. |

### Placement dependent on Phase 0 decisions

- Election-provider adapter filename/package and any provider SDK.
- Catalog import job: a Cloud Run Job module, admin router action, or reusable `smartervote_mcp` operation; prefer a durable/repeatable job over a scratch script.
- Official-boundary data files/bucket and TIGER/Line point-in-polygon service if Census APIs are insufficient.
- Partner/correction delivery adapter and CRM/mail provider.
- Product analytics aggregation: extend current Firestore/Cloudflare reporting or introduce a privacy-focused product analytics service.
- Feature-flag/config storage and reviewed `featured_race_ids`/campaign configuration.
- Social-card source template placement within the existing brand asset workflow.

## 27. Acceptance criteria

### Product and truthfulness

- At national-only launch, the homepage primary CTA is exactly **Explore national elections** and the hero clearly says state/local ballot coverage is unavailable. After the lookup gate passes, the primary CTA becomes exactly **Find my ballot** with the required incomplete-coverage disclosure and support link.
- Homepage progression covers value, lookup, real product proof, method, trust, exploration/impact, and restrained support; the full directory is secondary at `/elections/`.
- No public page claims “unbiased,” perfect neutrality, complete ballot coverage, guaranteed accuracy, nonprofit status, or tax deductibility.
- Lookup results use the four defined coverage states, never translate zero matches to “no elections,” and always link official resources where available.
- Demonstrations and metrics are derived from published production data, timestamped, deterministic, and omitted safely when unavailable.

### Lookup/data

- Autocomplete, geocoding, district resolution, election identification, and Smarter.Vote matching are separately implemented/tested behind adapters.
- Enabled geographies/categories meet Phase 0 gold-corpus accuracy/recall thresholds; provider, boundary vintage, confidence, and caveats are observable.
- Matching uses normalized exact identifiers or reviewed overrides; race-title fuzzy matching cannot create a public match.
- The catalog distinguishes discovered contests from published research and preserves source provenance/version history.
- Lookup provider failures, ambiguity, PO boxes, partial districts, no research, stale data, and official-only results have tested recovery paths.

### Privacy/security

- Full address/place token/coordinates never appear in URLs, Firestore durable records, analytics, logs, error reports, HTML metadata, or long-lived browser storage.
- Personalized responses are `no-store`; results are noindex and absent from sitemap; session/result expiry and deletion are tested.
- Sensitive endpoints use explicit public auth posture, validation, rate limits, quotas, abuse controls, redaction, restricted CORS, and cost alerts.
- Stripe prices/status are verified server-side, webhooks are signature-checked/idempotent, and no card data enters Smarter.Vote systems.

### Support and independence

- `/support/` and `/partners/` serve their distinct audiences; accounts are not required for payment or inquiry.
- LLC/non-tax-deductibility and editorial-independence disclosures appear before checkout/inquiry commitment.
- Published policy prohibits all specified influence and defines funding prioritization, conflicts, disclosure, recognition, and annual transparency reporting.
- Individual recognition is private by default/explicit opt-in; institutional sponsors use approved disclosure bands and program-level labels.
- One-time, monthly, cancellation, failed payment, refund, dispute, receipt, reconciliation, and test/live separation are operationally tested before general launch.

### Quality, accessibility, and operations

- Core lookup and payment journeys meet WCAG 2.2 AA and pass keyboard, NVDA, VoiceOver, mobile, zoom/reflow, contrast, focus, live-region, and reduced-motion checks.
- Static research pages retain performance/prerender/SEO behavior; new public routes have correct canonical/OG metadata; personalized and transactional routes are excluded.
- Unit, contract, integration, E2E, data-quality, security/privacy, accessibility, and full CI gates pass in staging/CI.
- Provider quotas and billing alerts, payment safeguards, monitoring, budgets, runbooks, retention jobs, named owners, rollback, and incident paths are exercised before launch. No custom Google billing kill switch is required.
- Canonical documentation is updated alongside each implemented behavior; no deploy, data publish, or payment activation occurs merely by following this plan.
