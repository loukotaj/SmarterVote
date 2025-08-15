"""
Source Discovery Engine for SmarterVote Pipeline (updated, with site walker)

Two-phase strategy:
  1) Core (evergreen, no freshness): Ballotpedia/FEC/OpenSecrets/Wikipedia/SoS + official campaign sites
     + depth-1 site walker on official campaign homepages to capture /issues, /platform, /news, /press, etc.
  2) Recency (fresh): candidate×issue news/social/debate, date-limited
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from shared import CanonicalIssue, FreshSearchQuery, RaceJSON, RaceMetadata, Source, SourceType

from ...providers import registry
from ...providers.base import TaskType
from ...utils.search_utils import SearchUtils
from ..constants import ALLOW as BASE_ALLOW
from ..constants import DENY as BASE_DENY

logger = logging.getLogger(__name__)


class SourceDiscoveryEngine:
    """Engine for discovering data sources about electoral races."""

    def __init__(self):
        self.seed_sources = {
            "ballotpedia": "https://ballotpedia.org",
            "fec": "https://www.fec.gov",
            "propublica": "https://www.propublica.org",
            "opensecrets": "https://www.opensecrets.org",
            "vote411": "https://www.vote411.org",
            "govtrack": "https://www.govtrack.us",
            "congress_gov": "https://www.congress.gov",
            "wikipedia": "https://www.wikipedia.org",
        }

        # TODO: Move to configuration
        self.search_config: Dict[str, Any] = {
            "top_results_per_query": 5,
            "num_queries_per_candidate": 10,  # tighter, higher-signal
            "freshness_days": 30,
            "quality_threshold": 0.7,
            "candidate_cap": 5,
            "issues": [
                CanonicalIssue.HEALTHCARE,
                CanonicalIssue.ECONOMY,
                CanonicalIssue.IMMIGRATION,
            ],
            "general_issue_terms": [
                CanonicalIssue.HEALTHCARE,
                CanonicalIssue.ECONOMY,
            ],
            "per_host_concurrency": 5,
            "cache_ttl_seconds": 300,
            # core flow knobs
            "require_campaign_homepage": True,
            "run_core_phase_first": True,
            "http_timeout_seconds": 20,
            # site walker knobs
            "site_walker_enabled": True,
            "site_walker_max_links_per_site": 8,
            "site_walker_timeout_seconds": 12,
            "site_walker_global_concurrency": 8,
        }

        # Initialize search utilities
        self.search_utils = SearchUtils(self.search_config)

    async def discover_all_sources(self, race_id: str, race_json: Optional[RaceJSON] = None) -> List[Source]:
        logger.info("Starting comprehensive source discovery for %s", race_id)
        rm = race_json.race_metadata if (race_json and race_json.race_metadata) else None

        core = await self.discover_core_sources(race_id, race_json)
        fresh = await self.discover_recency_sources(race_id, race_json)

        combined = self.search_utils.deduplicate_sources(core + fresh)

        # MINI MODEL PREFILTER right here, pre-fetch
        filtered = await self.prefilter_with_mini_model(race_id, combined, rm)

        # ensure official sites are pinned
        for s in filtered:
            if getattr(s, "is_official_campaign", False):
                s.score = max(s.score or 0, 0.99)

        return sorted(filtered, key=lambda s: (s.score or 0), reverse=True)

    async def discover_seed_sources(self, race_id: str, race_metadata: Optional[RaceMetadata] = None) -> List[Source]:
        """(Evergreen) Discover seed sources from known electoral databases."""
        return await self._discover_seed_sources(race_id, race_metadata)

    async def discover_fresh_issue_sources(self, race_id: str, race_json: Optional[RaceJSON] = None) -> List[Source]:
        """(Fresh) Discover issue-specific sources using Google Custom Search."""
        return await self._discover_fresh_issue_sources(race_id, race_json)

    async def discover_core_sources(self, race_id: str, race_json: Optional[RaceJSON]) -> List[Source]:
        """
        Phase 1 (Core): No freshness filters. Must capture:
          - Ballotpedia/Wikipedia race & candidate profiles
          - FEC/OpenSecrets (federal), SoS (state) pages
          - Official campaign homepage per candidate (if possible)
          - Vote411 (if available)
          - NEW: depth-1 campaign subpages via site walker (pre-fetch expansion)
        """
        rm = race_json.race_metadata if (race_json and race_json.race_metadata) else None

        # 1) Structured seeds (Ballotpedia/FEC/OpenSecrets/SoS)
        structured = await self._discover_seed_sources(race_id, rm)

        # 2) Trusted seed queries (Ballotpedia/Wikipedia/FEC by search)
        trusted_seed_queries = []
        if rm:
            trusted_seed_queries = self.search_utils.build_race_seed_queries(
                race_id=race_id,
                state=rm.state,
                office=rm.office_type,
                year=rm.year,
                district=rm.district,
                trusted_only=True,
            )
        trusted_results = await _run_queries(self.search_utils, trusted_seed_queries)

        # 3) Campaign site finder per candidate (no date filter)
        campaign_results: List[Source] = []
        if race_json and race_json.candidates:
            candidate_names = [c.name for c in race_json.candidates][: self.search_config.get("candidate_cap", 5)]
            campaign_queries = _build_campaign_site_queries(race_id, candidate_names, rm)
            campaign_results = await _run_queries(self.search_utils, campaign_queries)
            # Heuristic boost for likely official sites
            for s in campaign_results:
                if _looks_like_official_campaign(s):
                    s.score = max(s.score or 0, 0.98)
                    try:
                        setattr(s, "is_official_campaign", True)
                    except Exception:
                        pass

        # 3b) Expand official homepages with depth-1 site walker (HTML fetch, cheap)
        walked_subpages: List[Source] = []
        if self.search_config.get("site_walker_enabled", True) and campaign_results:
            walked_subpages = await self._expand_campaign_sites_with_walker(campaign_results)

        # 4) Vote411 & Wikipedia fallbacks by generic queries (no date)
        generic_queries = []
        if rm:
            generic_queries.extend(
                [
                    FreshSearchQuery(
                        text=f"site:vote411.org {rm.state} {rm.office_type} {rm.year}",
                        race_id=race_id,
                        issue=CanonicalIssue.GENERAL if hasattr(CanonicalIssue, "GENERAL") else next(iter(CanonicalIssue)),
                        generated_at=datetime.utcnow(),
                        max_results=5,
                        date_restrict="y2",  # 2 years is fine for evergreen directories
                    ),
                    FreshSearchQuery(
                        text=f"site:wikipedia.org {rm.year} {rm.state} {rm.office_type} election",
                        race_id=race_id,
                        issue=CanonicalIssue.GENERAL if hasattr(CanonicalIssue, "GENERAL") else next(iter(CanonicalIssue)),
                        generated_at=datetime.utcnow(),
                        max_results=5,
                        date_restrict="y2",
                    ),
                ]
            )
        generic_results = await _run_queries(self.search_utils, generic_queries)

        core_all = self.search_utils.deduplicate_sources(
            structured + trusted_results + campaign_results + walked_subpages + generic_results
        )

        # Optional: enforce campaign homepage coverage if configured (no-op for now)
        if self.search_config.get("require_campaign_homepage", True) and race_json and race_json.candidates:
            pass

        logger.info("Core phase collected %d sources", len(core_all))
        return core_all

    async def discover_recency_sources(self, race_id: str, race_json: Optional[RaceJSON]) -> List[Source]:
        """
        Phase 2 (Recency): date-limited, higher-churn content
        Reuses the existing _discover_fresh_issue_sources implementation.
        """
        fresh = await self._discover_fresh_issue_sources(race_id, race_json)
        logger.info("Recency phase collected %d sources", len(fresh))
        return fresh

    async def _discover_seed_sources(self, race_id: str, race_metadata: Optional[RaceMetadata] = None) -> List[Source]:
        """
        Discover sources from known electoral databases.

        NOTE: Do not assume SoS URL format; many states differ.
              Keep these as generic seeds; trusted searches will firm them up.
        """
        sources: List[Source] = []

        # Use metadata if available, otherwise parse race_id
        if race_metadata:
            state = race_metadata.state
            office_type = race_metadata.office_type
            year = race_metadata.year
            district = race_metadata.district
            race_type = race_metadata.race_type
        else:
            # Fallback to parsing race_id
            race_parts = race_id.split("-")
            if len(race_parts) >= 3:
                state = race_parts[0].upper()
                office_type = race_parts[1]
                year = int(race_parts[2]) if race_parts[2].isdigit() else int(race_parts[-1])
                district = race_parts[2] if len(race_parts) == 4 and race_parts[2].isdigit() else None
                race_type = "federal" if office_type in ["senate", "house"] else "state"
            else:
                logger.warning("Could not parse race_id %s, using minimal sources", race_id)
                return sources

        # Ballotpedia (basic constructed URL; trusted search will reinforce)
        if district:
            ballotpedia_url = f"https://ballotpedia.org/{year}_{state}_{office_type}_district_{district}_election"
        else:
            ballotpedia_url = f"https://ballotpedia.org/{year}_{state}_{office_type}_election"

        sources.append(
            Source(
                url=ballotpedia_url,
                type=SourceType.GOVERNMENT if hasattr(SourceType, "GOVERNMENT") else SourceType.WEBSITE,
                title=f"Ballotpedia - {state} {office_type.title()} Election {year}",
                description="Election overview (Ballotpedia)",
                last_accessed=datetime.utcnow(),
                is_fresh=False,
                score=0.7,
            )
        )

        # Federal races get FEC + OpenSecrets
        if race_type == "federal":
            if office_type == "senate":
                fec_url = f"https://www.fec.gov/data/elections/senate/{state.lower()}/{year}/"
            elif office_type == "house" and district:
                fec_url = f"https://www.fec.gov/data/elections/house/{state.lower()}/{district}/{year}/"
            else:
                fec_url = f"https://www.fec.gov/data/elections/{office_type.lower()}/{state.lower()}/{year}/"

            sources.append(
                Source(
                    url=fec_url,
                    type=SourceType.GOVERNMENT if hasattr(SourceType, "GOVERNMENT") else SourceType.WEBSITE,
                    title=f"FEC - {state} {office_type.title()} Election {year}",
                    description="Federal Election Commission data",
                    last_accessed=datetime.utcnow(),
                    is_fresh=False,
                    score=0.8,
                )
            )

            # Campaign finance (OpenSecrets) — heuristic URL as a seed only
            opensecrets_url = (
                f"https://www.opensecrets.org/races?cycle={year}&state={state.lower()}&chamber={office_type.lower()}"
            )
            sources.append(
                Source(
                    url=opensecrets_url,
                    type=SourceType.WEBSITE,
                    title=f"OpenSecrets - {state} {office_type.title()} Campaign Finance",
                    description="Campaign finance overview (OpenSecrets)",
                    last_accessed=datetime.utcnow(),
                    is_fresh=False,
                    score=0.7,
                )
            )
        else:
            # State-level SoS seed via generic domain pattern (not guaranteed)
            sos_url = f"https://www.sos.{state.lower()}.gov"
            sources.append(
                Source(
                    url=sos_url,
                    type=SourceType.GOVERNMENT if hasattr(SourceType, "GOVERNMENT") else SourceType.WEBSITE,
                    title=f"{state} Secretary of State",
                    description=f"Official {state} election information (root)",
                    last_accessed=datetime.utcnow(),
                    is_fresh=False,
                    score=0.6,
                )
            )

        logger.info("Generated %d seed sources for %s", len(sources), race_id)
        return sources

    # ----------------------------- Internal (fresh) --------------------------- #

    async def _discover_fresh_issue_sources(self, race_id: str, race_json: Optional[RaceJSON] = None) -> List[Source]:
        """Run candidate×issue searches (date-limited) and rank results."""
        issues = self.search_config.get("issues", list(CanonicalIssue))
        candidate_cap = self.search_config.get("candidate_cap", 3)
        query_limit = self.search_config.get("num_queries_per_candidate", 10)
        top_results = self.search_config.get("top_results_per_query", 5)

        if race_json and race_json.candidates:
            candidates = [c.name for c in race_json.candidates][:candidate_cap]
            race_meta = race_json.race_metadata
        else:
            candidates = []
            race_meta = race_json.race_metadata if race_json else None

        all_sources: List[Source] = []

        # Candidate × issue (smarter templates are inside SearchUtils; limit reduced)
        for cand in candidates:
            queries = self.search_utils.generate_candidate_issue_queries(race_id, cand, issues, race_meta, query_limit)
            results_nested = (
                await asyncio.gather(*[self.search_utils.search_google_custom(q, q.issue) for q in queries]) if queries else []
            )
            flat = [s for r in results_nested for s in r]

            # Score nudges for news/social vs blogs (cheap heuristics)
            for s in flat:
                host = (str(s.url) or "").lower()
                if "youtube.com" in host or "twitter.com" in host or "facebook.com" in host:
                    s.score = max(s.score or 0, 0.68)
                elif ".gov" in host or "fec.gov" in host:
                    s.score = max(s.score or 0, 0.75)
                else:
                    s.score = max(s.score or 0, 0.6)

            deduped = self.search_utils.deduplicate_sources(flat)
            all_sources.extend(sorted(deduped, key=lambda s: s.score or 0, reverse=True))

        # Race-level general issue sweeps (few, fresh)
        general_issues: Iterable[CanonicalIssue] = self.search_config.get("general_issue_terms", [])
        for issue in general_issues:
            q = self.search_utils.generate_issue_query(
                race_id,
                issue,
                state=getattr(race_meta, "state", None),
                office=getattr(race_meta, "office_type", None),
            )
            q.max_results = top_results
            all_sources.extend(await self.search_utils.search_google_custom(q, issue))

        deduped_all = self.search_utils.deduplicate_sources(all_sources)
        return sorted(deduped_all, key=lambda s: s.score or 0, reverse=True)

    # ----------------------------- Site Walker --------------------------- #

    async def _expand_campaign_sites_with_walker(self, campaign_sources: List[Source]) -> List[Source]:
        """
        For each likely official campaign homepage, fetch HTML and extract same-domain,
        depth-1 subpages that look like issues/platform/news/press/about.
        Returns additional Source objects (pre-fetch expansion).
        """
        timeout_s = int(self.search_config.get("site_walker_timeout_seconds", 12))
        max_links = int(self.search_config.get("site_walker_max_links_per_site", 8))
        global_concurrency = int(self.search_config.get("site_walker_global_concurrency", 8))

        sem = asyncio.Semaphore(global_concurrency)
        out: List[Source] = []

        async with httpx.AsyncClient(
            timeout=timeout_s, follow_redirects=True, headers={"User-Agent": "SmarterVoteBot/1.0"}
        ) as client:

            async def process(src: Source):
                if not _looks_like_official_campaign(src):
                    return
                # best effort HTML GET
                try:
                    async with sem:
                        html = await self._fetch_html(client, src.url)
                except Exception as e:
                    logger.debug("Site walker fetch failed for %s: %s", src.url, e)
                    return
                if not html:
                    return
                derived = self._derive_candidate_pages(src, html, max_links=max_links)
                # score: below homepage, above most other sources
                for s in derived:
                    s.score = max(s.score or 0, min((src.score or 0.95) - 0.03, 0.94))
                    s.is_fresh = False
                    # keep a hint for later stages if needed
                    try:
                        setattr(s, "is_campaign_subpage", True)
                    except Exception:
                        pass
                out.extend(derived)

            await asyncio.gather(*[process(s) for s in campaign_sources])

        # de-dup within walker outputs
        deduped = self.search_utils.deduplicate_sources(out)
        logger.info("Site walker discovered %d campaign subpages", len(deduped))
        return deduped

    async def _fetch_html(self, client: httpx.AsyncClient, url: Optional[str]) -> str:
        if not url:
            return ""
        try:
            r = await client.get(url)
            ct = (r.headers.get("content-type") or "").lower()
            if "text/html" not in ct and "html" not in ct:
                return ""
            return r.text or ""
        except Exception as e:
            logger.debug("HTTP GET failed for %s: %s", url, e)
            return ""

    def _derive_candidate_pages(self, homepage: Source, html: str, *, max_links: int = 8) -> List[Source]:
        """Extract same-domain links that look like issues/platform/news/press/about."""
        if not homepage or not getattr(homepage, "url", None) or not html:
            return []
        base = homepage.url
        host = urlparse(base).netloc
        soup = BeautifulSoup(html, "html.parser")

        ALLOW = BASE_ALLOW + ("/policies", "/media", "/updates")
        DENY = BASE_DENY + ("/sitemap", "/subscribe", "/merch", "/cart", "/donation")

        out: List[Source] = []
        seen: set[str] = set()

        def keep(path: str) -> bool:
            p = path.lower()
            if any(p.startswith(d) for d in DENY):
                return False
            if any(p.startswith(a) for a in ALLOW):
                return True
            # common variations
            return any(x in p for x in ("/issue", "/policy", "/plan", "/press", "/news", "/about"))

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
                continue
            link = urljoin(base, href)
            parsed = urlparse(link)
            if parsed.netloc != host:
                continue
            if not keep(parsed.path):
                continue
            if link in seen:
                continue
            seen.add(link)
            title = (a.get_text() or "").strip()
            out.append(
                Source(
                    url=link,
                    type=SourceType.WEBSITE,
                    title=title or "Campaign subpage",
                    description="Likely campaign issues/press/about page",
                    last_accessed=datetime.utcnow(),
                    is_fresh=False,
                    score=0.9,
                )
            )
            if len(out) >= max_links:
                break

        return out

    # ----------------------------- Mini-model prefilter --------------------------- #

    async def prefilter_with_mini_model(
        self,
        race_id: str,
        sources: List[Source],
        race_meta: Optional[RaceMetadata],
        *,
        batch_size: int = 18,
        drop_threshold: float = 0.35,
        boost_threshold: float = 0.75,
    ) -> List[Source]:
        if not sources:
            return sources

        ctx_parts = []
        if race_meta:
            ctx_parts.append(f"state={race_meta.state}")
            ctx_parts.append(f"office={race_meta.office_type}")
            ctx_parts.append(f"year={race_meta.year}")
            if getattr(race_meta, "district", None):
                ctx_parts.append(f"district={race_meta.district}")
        ctx = ", ".join(ctx_parts) or "state=?, office=?, year=?"

        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["i", "keep", "priority", "category", "official"],
                        "properties": {
                            "i": {"type": "integer"},  # index in the batch
                            "keep": {"type": "boolean"},  # fetch or drop
                            "priority": {"type": "number"},  # 0.0-1.0 suggested
                            "category": {"type": "string"},  # campaign|gov|news|social|blog|spam|other
                            "official": {"type": "boolean"},  # likely official campaign site
                            "notes": {"type": "string"},
                        },
                    },
                }
            },
            "additionalProperties": False,
        }

        def build_prompt(batch: List[Source], start_idx: int) -> str:
            lines = [
                "You are triaging URLs about an election. Return JSON only per schema.",
                f"Race context: {ctx}.",
                "Label each URL with: keep, priority (0-1), category, official (campaign site?).",
                "Prefer: official campaign sites, Ballotpedia/FEC/OpenSecrets/SoS, reputable local/state news.",
                "Demote: spam, SEO blogs, irrelevant homonyms, fundraising aggregators without first-party info.",
                "",
                "BATCH:",
            ]
            for j, s in enumerate(batch):
                title = (s.title or "").strip()
                lines.append(f"{j}. url={s.url} | title={title}")
            lines.append("\nReturn strictly the JSON for {items:[...]}.")
            return "\n".join(lines)

        out: List[Source] = []
        for start in range(0, len(sources), batch_size):
            batch = sources[start : start + batch_size]
            prompt = build_prompt(batch, start_idx=start)

            data = await registry.generate_json(
                TaskType.DISCOVER,
                prompt,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "Source Discovery Engine",
                        "schema": schema,
                        "strict": True,  # keep the model pinned to your schema
                    },
                },
                max_tokens=1200,
                allow_repair=True,
                repair_schema_hint=str(schema),
            )

            by_local_idx: Dict[int, Dict[str, Any]] = {
                item["i"]: item for item in data.get("items", []) if isinstance(item, dict) and "i" in item
            }
            for j, src in enumerate(batch):
                ann = by_local_idx.get(j)
                if not ann:
                    # if model didn't return an entry, keep but with minimal priority shaping
                    out.append(src)
                    continue

                pr = float(max(0.0, min(1.0, ann.get("priority", 0.5))))
                keep = bool(ann.get("keep", True))
                cat = (ann.get("category") or "").lower()
                official = bool(ann.get("official", False))

                base = src.score or 0.5
                if cat in ("campaign",):
                    base = max(base, 0.85)
                elif cat in ("gov", "fec", "opensecrets", "ballotpedia", "wikipedia", "sos"):
                    base = max(base, 0.8)
                elif cat in ("news", "localnews"):
                    base = max(base, 0.65)
                elif cat in ("social",):
                    base = max(base, 0.6)
                elif cat in ("spam",):
                    base = min(base, 0.2)

                # blend model priority (weighted)
                src.score = 0.6 * base + 0.4 * pr

                # pin likely official homepage
                if official:
                    try:
                        setattr(src, "is_official_campaign", True)
                    except Exception:
                        pass
                    src.score = max(src.score, 0.98)

                # final keep/drop
                if keep and src.score >= drop_threshold:
                    out.append(src)
                else:
                    # drop only if both say "no" and score is very low
                    if src.score >= drop_threshold * 0.6:
                        out.append(src)

        # light re-rank: strong keeps first
        out.sort(key=lambda s: (s.score or 0), reverse=True)
        return out


# ----------------------------- Helpers --------------------------- #


def _build_campaign_site_queries(
    race_id: str,
    candidate_names: List[str],
    rm: Optional[RaceMetadata],
) -> List[FreshSearchQuery]:
    """Craft high-signal, no-freshness templates to capture official homepages + socials."""
    if not candidate_names:
        return []

    state = getattr(rm, "state", "") if rm else ""
    office = getattr(rm, "office_type", "") if rm else ""
    year = getattr(rm, "year", "") if rm else ""

    templates = [
        '"{name}" ("for {office}" OR campaign OR "official site") {state}',
        'intitle:"{name}" ("for {office}" OR "for {office} {state}")',
        '"{name}" site:.com OR site:.org',
        # socials as pivots (no freshness)
        '"{name}" ("for {office}" OR campaign) site:facebook.com',
        '"{name}" ("for {office}" OR campaign) site:twitter.com',
        '"{name}" ("for {office}" OR campaign) site:youtube.com',
        # directories that often list the official link
        '"{name}" Ballotpedia',
        '"{name}" OpenSecrets',
    ]

    out: List[FreshSearchQuery] = []
    for name in candidate_names:
        for t in templates:
            text = t.format(name=name, office=office, state=state, year=year)
            out.append(
                FreshSearchQuery(
                    text=text,
                    race_id=race_id,
                    issue=CanonicalIssue.GENERAL if hasattr(CanonicalIssue, "GENERAL") else next(iter(CanonicalIssue)),
                    generated_at=datetime.utcnow(),
                    max_results=5,
                    # no dateRestrict => evergreen
                )
            )
    return out


def _looks_like_official_campaign(src: Source) -> bool:
    """Cheap heuristic to identify campaign homepages using only the URL/title."""
    if not src or not src.url:
        return False
    u = str(src.url) if src.url else ""
    title = (src.title or "").lower()

    # Avoid socials; we want the campaign site itself here
    if any(s in u for s in ["facebook.com", "twitter.com", "x.com", "youtube.com", "tiktok.com"]):
        return False

    tokens = ["for", "elect", "vote", "campaign", "donate", "volunteer"]
    domain_tokens = ["for", "elect", "vote", "4"]
    looks_campaign_domain = any(f".{tok}" in u or f"{tok}" in u for tok in domain_tokens)
    looks_campaign_title = any(tok in title for tok in tokens)

    # prefer apex domains ending in .com/.org and not .gov/.edu/news
    good_tld = u.endswith(".com") or u.endswith(".org") or ".com/" in u or ".org/" in u
    bad_tld = u.endswith(".gov") or ".gov/" in u or "/news" in u

    return (looks_campaign_domain or looks_campaign_title) and good_tld and not bad_tld


async def _run_queries(search_utils: SearchUtils, queries: List[FreshSearchQuery]) -> List[Source]:
    if not queries:
        return []
    # Run with concurrency via SearchUtils
    results_nested = await asyncio.gather(*[search_utils.search_general(q) for q in queries])
    flat = [s for r in results_nested for s in r]
    return search_utils.deduplicate_sources(flat)
