"""Search utilities for source discovery in SmarterVote Pipeline.

Backwards-compatibility notes
- Public methods kept: search_google_custom, search_candidate_info, search_general,
  generate_issue_query, generate_candidate_query, generate_candidate_issue_queries,
  deduplicate_sources.
- Added helpers are additive and safe for other services to ignore.
"""

import asyncio
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..schema import CanonicalIssue, FreshSearchQuery, RaceMetadata, Source, SourceType

logger = logging.getLogger(__name__)


class SearchUtils:
    """Utilities for performing searches to discover sources."""

    # --- static maps / constants (small, local, no external deps) --- #

    _STATE_MAP: Dict[str, str] = {
        "AL": "Alabama",
        "AK": "Alaska",
        "AZ": "Arizona",
        "AR": "Arkansas",
        "CA": "California",
        "CO": "Colorado",
        "CT": "Connecticut",
        "DE": "Delaware",
        "FL": "Florida",
        "GA": "Georgia",
        "HI": "Hawaii",
        "ID": "Idaho",
        "IL": "Illinois",
        "IN": "Indiana",
        "IA": "Iowa",
        "KS": "Kansas",
        "KY": "Kentucky",
        "LA": "Louisiana",
        "ME": "Maine",
        "MD": "Maryland",
        "MA": "Massachusetts",
        "MI": "Michigan",
        "MN": "Minnesota",
        "MS": "Mississippi",
        "MO": "Missouri",
        "MT": "Montana",
        "NE": "Nebraska",
        "NV": "Nevada",
        "NH": "New Hampshire",
        "NJ": "New Jersey",
        "NM": "New Mexico",
        "NY": "New York",
        "NC": "North Carolina",
        "ND": "North Dakota",
        "OH": "Ohio",
        "OK": "Oklahoma",
        "OR": "Oregon",
        "PA": "Pennsylvania",
        "RI": "Rhode Island",
        "SC": "South Carolina",
        "SD": "South Dakota",
        "TN": "Tennessee",
        "TX": "Texas",
        "UT": "Utah",
        "VT": "Vermont",
        "VA": "Virginia",
        "WA": "Washington",
        "WV": "West Virginia",
        "WI": "Wisconsin",
        "WY": "Wyoming",
        "DC": "District of Columbia",
        "PR": "Puerto Rico",
    }

    _NEG_OFFICE_FOR_US_SENATE = [
        r"\bstate senate\b",
        r"\bstate\s+legislature\b",
        r"\bgeneral assembly\b",
        r"\bhouse district\b",
        r"\bcounty commission(er)?\b",
        r"\bcity council\b",
        r"\bstate representative\b",
    ]

    def __init__(self, search_config: dict):
        """Initialize with search configuration."""
        self.search_config = search_config
        self.cache: Dict[str, Tuple[datetime, List[Source]]] = {}
        self.cache_ttl = search_config.get("cache_ttl_seconds", 300)
        self.per_host_concurrency = search_config.get("per_host_concurrency", 5)
        self._host_semaphores: Dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(self.per_host_concurrency))

        # Basic domain trust ranking (explicit hosts; TLDs handled in _score_source)
        self.domain_trust: Dict[str, float] = {
            "fec.gov": 0.95,
            "ballotpedia.org": 0.90,
            "opensecrets.org": 0.90,
        }

        # Canonical issue synonyms
        self.issue_synonyms: Dict[CanonicalIssue, List[str]] = {
            CanonicalIssue.HEALTHCARE: ["health care", "medical", "medicare", "medicaid"],
            CanonicalIssue.ECONOMY: ["economic", "jobs", "employment", "taxes", "budget"],
            CanonicalIssue.CLIMATE_ENERGY: ["climate change", "environment", "renewable energy", "fossil fuels"],
            CanonicalIssue.REPRODUCTIVE_RIGHTS: ["abortion", "reproductive health", "family planning"],
            CanonicalIssue.IMMIGRATION: ["border", "refugees", "citizenship", "visa"],
            CanonicalIssue.GUNS_SAFETY: ["gun control", "firearms", "second amendment", "gun violence"],
            CanonicalIssue.FOREIGN_POLICY: ["international", "defense", "military", "diplomacy"],
            CanonicalIssue.SOCIAL_JUSTICE: [
                "LGBTQ",
                "gay rights",
                "transgender",
                "equality",
                "civil rights",
                "racial justice",
                "gender equality",
                "disability rights",
            ],
            CanonicalIssue.EDUCATION: ["schools", "teachers", "students", "university"],
            CanonicalIssue.TECH_AI: ["technology", "artificial intelligence", "privacy", "internet"],
            CanonicalIssue.ELECTION_REFORM: ["voting rights", "gerrymandering", "campaign finance"],
        }

    # ------------------------- public search APIs ------------------------- #

    async def search_google_custom(self, query: FreshSearchQuery, issue: CanonicalIssue) -> List[Source]:
        """Perform Google Custom Search with light caching, concurrency and scoring + race-aware post-filter."""
        cache_key = f"{query.race_id}:{query.text}"
        now = datetime.utcnow()
        cached = self.cache.get(cache_key)
        if cached and now - cached[0] < timedelta(seconds=self.cache_ttl):
            return cached[1]

        api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

        if not api_key or not search_engine_id:
            logger.warning(
                "Google Custom Search API not configured (missing GOOGLE_SEARCH_API_KEY or GOOGLE_SEARCH_ENGINE_ID)"
            )
            logger.info("Would search Google for: %s", query.text)

            mock_source = Source(
                url=f"https://example.com/news/{(getattr(issue, 'value', str(issue))).lower()}-{query.race_id}",
                type=self._choose_type("WEBSITE"),
                title=f"Fresh: {getattr(issue, 'value', str(issue))} in {query.race_id}",
                description=f"Fresh search content about {getattr(issue, 'value', str(issue))} for this race",
                last_accessed=now,
                published_at=now,
                score=0.5,
                scoring_reason="mock",
                is_fresh=True,
            )
            self.cache[cache_key] = (now, [mock_source])
            return [mock_source]

        # Derive race context from race_id (tolerant of partials)
        race_ctx = self._race_context_from_race_id(getattr(query, "race_id", None))

        # If the query explicitly targets Ballotpedia/Wikipedia, prefer relevance over date sorting
        force_relevance = any(site in (query.text or "").lower() for site in ("site:ballotpedia.org", "site:wikipedia.org"))

        logger.info("Searching Google Custom Search for: %s", query.text)

        try:
            import httpx  # type: ignore
        except ImportError:
            logger.warning("httpx not available for Google search. Using mock results.")
            mock_source = Source(
                url=f"https://example.com/mock/{(getattr(issue, 'value', str(issue))).lower()}-{query.race_id}",
                type=self._choose_type("WEBSITE"),
                title=f"Mock: {getattr(issue, 'value', str(issue))} in {query.race_id}",
                description=f"Mock search content about {getattr(issue, 'value', str(issue))} for this race",
                last_accessed=now,
                published_at=now,
                score=0.5,
                scoring_reason="mock",
                is_fresh=True,
            )
            self.cache[cache_key] = (now, [mock_source])
            return [mock_source]

        search_url = "https://www.googleapis.com/customsearch/v1"

        # Respect query overrides for freshness and num
        date_restrict = getattr(query, "date_restrict", None)
        date_param = date_restrict if date_restrict else f"d{self.search_config.get('freshness_days', 30)}"
        num = getattr(query, "max_results", None) or self.search_config.get("max_results_per_query", 10)

        params = {
            "key": api_key,
            "cx": search_engine_id,
            "q": query.text,
            "num": num,
            "dateRestrict": date_param,
        }
        if not force_relevance:
            params["sort"] = "date"

        host = urlparse(search_url).netloc
        async with self._host_semaphores[host]:
            try:
                async with httpx.AsyncClient(timeout=self.search_config.get("http_timeout_seconds", 20)) as client:
                    response = await client.get(search_url, params=params)
                    response.raise_for_status()
                    data = response.json()
            except Exception as e:  # noqa: BLE001
                logger.error("Google Custom Search failed for %s | error=%s", query.text, e)
                return []

        strict = bool(getattr(query, "strict", self.search_config.get("strict_seed_filter", True)))

        sources: List[Source] = []
        for item in data.get("items", []) or []:
            link = item.get("link")
            if not link:
                continue

            link_norm = self._normalize_url(link)
            title = item.get("title", "") or ""
            snippet = item.get("snippet", "") or ""

            # Race-aware gating (state/year/office; plus negative keyword rules)
            gate_res = self._race_gate(link_norm, title, snippet, race_ctx)

            # If strict, drop non-matching or conflicting results early
            if strict and not gate_res["pass"]:
                logger.debug(
                    "Dropping result (strict): reason=%s | url=%s",
                    ",".join(gate_res["reasons"]) or "unknown",
                    link_norm,
                )
                continue

            published_at = self._extract_published_time(item)
            source_type = self._classify_source(link_norm)

            base_score, reason = self._score_source(link_norm, title, snippet, published_at, race_ctx.get("state"))
            # Boost/penalize by gate strength even if not strict
            boost = gate_res["match_strength"]  # 0.0 - 0.5 range
            penalty = gate_res["penalty"]  # 0.0 - 0.4 range
            final_score = max(0.0, min(1.0, base_score + boost - penalty))
            full_reason = f"{reason}; race_gate={gate_res['summary']}; boost={boost:.2f}; penalty={penalty:.2f}"

            sources.append(
                Source(
                    url=link_norm,
                    type=source_type,
                    title=title,
                    description=snippet,
                    last_accessed=now,
                    published_at=published_at,
                    score=final_score,
                    scoring_reason=full_reason,
                    is_fresh=True,
                )
            )

        # Deduplicate and score-sort
        sources = self.deduplicate_sources(sources)
        sources.sort(key=lambda s: s.score or 0.0, reverse=True)

        self.cache[cache_key] = (datetime.utcnow(), sources)
        return sources

    async def search_candidate_info(self, query: FreshSearchQuery) -> List[Source]:
        """Search for candidate-specific information (kept for compatibility)."""
        issue = self._pick_issue("GENERAL")
        return await self.search_google_custom(query, issue)

    async def search_general(self, query: FreshSearchQuery) -> List[Source]:
        """Perform a general search without requiring a specific canonical issue."""
        issue = self._pick_issue("GENERAL")
        return await self.search_google_custom(query, issue)

    # ------------------------- query generation ------------------------- #

    def generate_issue_query(
        self,
        race_id: str,
        issue: CanonicalIssue,
        candidate_names: List[str] = None,
        state: str = None,
        office: str = None,
    ) -> FreshSearchQuery:
        """Generate a targeted search query for a specific issue."""
        query_parts = [issue.value]

        if state:
            query_parts.append(state)
        if office:
            query_parts.append(office)

        if candidate_names:
            candidates_part = " OR ".join(f'"{name}"' for name in candidate_names[:3])
            query_parts.append(f"({candidates_part})")

        query_text = " ".join(query_parts)
        query_text += " -site:wikipedia.org -site:reddit.com -site:twitter.com"

        return FreshSearchQuery(
            text=query_text,
            race_id=race_id,
            issue=issue,
            generated_at=datetime.utcnow(),
        )

    def generate_candidate_query(self, race_id: str, candidate_name: str) -> FreshSearchQuery:
        """Generate a search query specifically for a candidate."""
        parts = (race_id or "").split("-")
        state = parts[0] if len(parts) > 0 else ""
        office = parts[1] if len(parts) > 1 else ""
        query_text = f'"{candidate_name}" candidate {state} {office} -site:wikipedia.org -obituary -death'

        return FreshSearchQuery(
            text=query_text,
            race_id=race_id,
            issue=self._pick_issue("GENERAL"),
            generated_at=datetime.utcnow(),
        )

    def generate_candidate_issue_queries(
        self,
        race_id: str,
        candidate_name: str,
        issue: CanonicalIssue,
        race_metadata: Optional[RaceMetadata],
        sites: List[str],
    ) -> List[FreshSearchQuery]:
        """Generate base and site-specific queries for candidate×issue searches."""
        state = None
        year: Optional[str] = None
        district: Optional[str] = None

        if race_metadata:
            state = race_metadata.state
            year = str(race_metadata.year)
            district = race_metadata.district
        else:
            parts = race_id.split("-") if race_id else []
            if parts:
                state = parts[0]
            if len(parts) >= 3 and parts[-1].isdigit():
                year = parts[-1]

        issue_terms = [issue.value.lower()] + self.issue_synonyms.get(issue, [])
        issue_part = "(" + " OR ".join(issue_terms) + ")"

        base = f'"{candidate_name}" {issue_part}'
        if state:
            base += f" {state}"
        if district:
            base += f" {district}"
        if year:
            base += f" {year}"

        queries = [FreshSearchQuery(text=base, race_id=race_id, issue=issue, generated_at=datetime.utcnow())]
        for site in sites:
            queries.append(
                FreshSearchQuery(text=f"{base} site:{site}", race_id=race_id, issue=issue, generated_at=datetime.utcnow())
            )
        return queries

    # ------------------------- new helpers (additive) ------------------------- #

    def is_trusted_domain(self, url: str) -> bool:
        """Public helper: whether a URL is on a trusted election info domain."""
        try:
            host = urlparse(url).netloc.lower().removeprefix("www.")
            if host.endswith(".gov"):
                return True
            return host in self.domain_trust or any(host.endswith("." + d) for d in self.domain_trust)
        except Exception:
            return False

    def canonicalize_url(self, url: str) -> str:
        """Public helper: aggressive URL canonicalization (safe to use elsewhere)."""
        return self._normalize_url(url)

    def build_race_seed_queries(
        self,
        race_id: str,
        state: str,
        office: str,
        year: int,
        district: Optional[str],
        trusted_only: bool = True,
    ) -> List[FreshSearchQuery]:
        """Build a small set of seed queries for a race (trusted-first or permissive)."""
        state_part = state
        district_text = ""
        if district:
            district_text = " at-large" if str(district).upper() == "AL" else f" district {district}"

        targets = []
        if trusted_only:
            targets = [
                f"site:ballotpedia.org {year} {state_part}{district_text} {office} election",
                f"site:wikipedia.org {year} {state_part}{district_text} {office} election",
            ]
            if office in {"senate", "house"}:
                targets.append(f"site:fec.gov {year} {state} {office} candidates")
        else:
            base = f"{year} {state_part}{district_text} {office}"
            targets = [
                f"{base} candidates",
                f"{base} candidate list",
                f"{base} ballotpedia OR wikipedia OR site:.gov",
                f"{base} official campaign website",
            ]

        out: List[FreshSearchQuery] = []
        for t in targets:
            out.append(
                FreshSearchQuery(
                    text=t,
                    race_id=race_id,
                    issue=self._pick_issue("GENERAL"),
                    generated_at=datetime.utcnow(),
                    max_results=10,
                    date_restrict="y2",
                    strict=True,  # enforce post-filter for seed
                )
            )
        return out

    # ------------------------- utilities ------------------------- #

    def deduplicate_sources(self, sources: List[Source]) -> List[Source]:
        """Remove duplicate sources with aggressive URL normalization."""
        seen: Set[str] = set()
        seen_titles: Set[str] = set()
        unique_sources: List[Source] = []

        for src in sources:
            normalized = self._normalize_url(str(src.url))
            title_key = urlparse(normalized).netloc + "|" + re.sub(r"\s+", " ", (src.title or "").lower())
            if normalized in seen or title_key in seen_titles:
                continue
            seen.add(normalized)
            seen_titles.add(title_key)
            unique_sources.append(src)

        return unique_sources

    # ------------------------- internal helpers ------------------------- #

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        scheme = (parsed.scheme or "https").lower()
        netloc = parsed.netloc.lower().lstrip(".")
        # Drop common mobile subdomain
        if netloc.startswith("m."):
            netloc = netloc[2:]
        # Strip default ports
        netloc = netloc.replace(":80", "").replace(":443", "")
        # Normalize path variants (amp/mobile/print)
        path = re.sub(r"/(amp|mobile|print)/?", "/", (parsed.path or "/"))
        # Strip fragments
        fragmentless = (scheme, netloc, path.rstrip("/"), "", "", "")
        # Strip noisy tracking params
        query_pairs = [
            (k, v)
            for k, v in parse_qsl(parsed.query or "", keep_blank_values=True)
            if not k.lower().startswith(("utm_", "gclid", "fbclid", "mc_cid", "mc_eid", "ref"))
            and k.lower() not in {"amp", "amp_js_v"}
        ]
        return urlunparse((scheme, netloc, path.rstrip("/"), "", urlencode(query_pairs), ""))

    def _extract_published_time(self, item: Dict[str, Any]) -> Optional[datetime]:  # noqa: ANN401
        pagemap = item.get("pagemap", {}) or {}
        date_str: Optional[str] = None

        # Common metatags
        for tag in pagemap.get("metatags", []) or []:
            date_str = (
                tag.get("article:published_time")
                or tag.get("pubdate")
                or tag.get("date")
                or tag.get("dc.date.issued")
                or tag.get("og:updated_time")
            )
            if date_str:
                break

        # Schema.org overlays
        if not date_str:
            if "newsarticle" in pagemap:
                date_str = (pagemap["newsarticle"][0] or {}).get("datepublished")
            elif "article" in pagemap:
                date_str = (pagemap["article"][0] or {}).get("datepublished")

        if not date_str:
            return None

        try:
            # Normalize trailing Z
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return None

    def _classify_source(self, url: str) -> SourceType:
        domain = urlparse(url).netloc.lower()
        if domain.endswith(".gov") or "fec.gov" in domain:
            return self._choose_type("GOVERNMENT")
        if any(social in domain for social in ["twitter.com", "facebook.com", "youtube.com", "tiktok.com"]):
            return self._choose_type("SOCIAL_MEDIA")
        if url.lower().endswith(".pdf"):
            return self._choose_type("PDF")
        return self._choose_type("WEBSITE")

    def _choose_type(self, preferred: str) -> SourceType:
        """Always return a valid SourceType, tolerating enum name drift across services."""
        if hasattr(SourceType, preferred):
            return getattr(SourceType, preferred)
        for alt in ("WEBSITE", "WEB", "URL", "ARTICLE", "UNKNOWN"):
            if hasattr(SourceType, alt):
                return getattr(SourceType, alt)
        try:
            return next(iter(SourceType))
        except Exception as e:  # noqa: BLE001
            raise AttributeError("SourceType enum has no accessible members") from e

    def _score_source(
        self,
        url: str,
        title: str,
        snippet: str,
        published_at: Optional[datetime],
        state: Optional[str],
    ) -> Tuple[float, str]:
        """Return (score, reason) using domain trust, freshness, locality, and type."""
        domain = urlparse(url).netloc.lower()
        reason: List[str] = []

        # Domain trust
        trust = 0.5
        if domain in self.domain_trust:
            trust = self.domain_trust[domain]
            reason.append(f"trust=domain({trust:.2f})")
        elif domain.endswith(".gov"):
            trust = 1.0
            reason.append("trust=tld(gov)")
        elif domain.endswith(".edu"):
            trust = 0.9
            reason.append("trust=tld(edu)")
        elif any(domain.endswith(k) for k in self.domain_trust):
            match = next(k for k in self.domain_trust if domain.endswith(k))
            trust = self.domain_trust[match]
            reason.append(f"trust=parent({match})")
        else:
            reason.append("trust=other")

        score = trust

        # Freshness
        fresh_window = self.search_config.get("freshness_days", 30)
        if published_at:
            if (datetime.utcnow() - published_at).days <= fresh_window:
                score += 0.1
                reason.append("fresh=Y")
            else:
                reason.append("fresh=N")
        else:
            reason.append("fresh=?")

        # Localness (light)
        local_bonus = 0.0
        if state:
            state_l = state.lower()
            combined = " ".join([url.lower(), (title or "").lower(), (snippet or "").lower()])
            if state_l in combined or self._STATE_MAP.get(state.upper(), "").lower() in combined:
                local_bonus = 0.1
        reason.append(f"local={local_bonus:.1f}")
        score += local_bonus

        # Type bonus
        source_type = self._classify_source(url)
        if source_type in {self._choose_type("GOVERNMENT"), self._choose_type("PDF")}:
            score += 0.1
            reason.append("type=bonus")
        else:
            reason.append(f"type={getattr(source_type, 'value', str(source_type))}")

        return min(score, 1.0), "; ".join(reason)

    # ---- race-aware post-filter & context helpers ---- #

    def _race_context_from_race_id(self, race_id: Optional[str]) -> Dict[str, Any]:
        """Parse 'mo-senate-2024' into a context dict. Be tolerant if missing pieces."""
        out = {"race_id": race_id, "state": None, "state_name": None, "year": None, "office": None}
        if not race_id:
            return out
        parts = [p for p in (race_id or "").split("-") if p]
        if len(parts) >= 1 and len(parts[0]) in (2, 3):
            out["state"] = parts[0].upper()
            out["state_name"] = self._STATE_MAP.get(out["state"])
        if len(parts) >= 2:
            out["office"] = parts[1].lower()
        if len(parts) >= 3 and parts[-1].isdigit():
            out["year"] = int(parts[-1])
        return out

    def _race_gate(self, url: str, title: str, snippet: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Race-aware gating + match strength. Returns dict with pass, reasons, match_strength, penalty, summary."""
        reasons: List[str] = []
        penalty = 0.0
        boost = 0.0

        combined_lower = " ".join([url.lower(), title.lower(), snippet.lower()])

        # No context → neutral pass
        if not ctx or not ctx.get("state") or not ctx.get("year") or not ctx.get("office"):
            return {"pass": True, "reasons": [], "match_strength": 0.0, "penalty": 0.0, "summary": "no_ctx"}

        state = ctx["state"]
        state_name = (ctx.get("state_name") or "").lower()
        year = ctx["year"]
        office = (ctx["office"] or "").lower()

        # 1) Year presence (required but forgiving for evergreen pages like Ballotpedia/Wiki)
        year_present = str(year) in combined_lower
        if not year_present and not any(h in url for h in ("ballotpedia.org", "wikipedia.org", "fec.gov")):
            reasons.append("year_miss")
            penalty += 0.15

        # 2) State presence
        state_hit = state.lower() in combined_lower or (state_name and state_name in combined_lower)
        if not state_hit:
            reasons.append("state_miss")
            penalty += 0.2

        # 3) Office alignment
        office_ok = self._office_match(office, combined_lower)
        if not office_ok:
            reasons.append("office_miss")
            penalty += 0.2

        # 4) Negative keywords for US Senate to avoid state legislature bleed
        if office in ("senate", "us-senate", "u.s.-senate", "ussenate", "us_senate"):
            for pat in self._NEG_OFFICE_FOR_US_SENATE:
                if re.search(pat, combined_lower, flags=re.IGNORECASE):
                    reasons.append("neg_keyword:" + pat)
                    penalty += 0.2
                    break

        # 5) Other state leakage (mention of a different state is a red flag)
        other_state = self._detect_other_state_hit(combined_lower, state)
        if other_state:
            reasons.append(f"other_state:{other_state}")
            penalty += 0.25

        # 6) Canonical slug check for Ballotpedia/Wikipedia (strong positive)
        if any(h in url for h in ("ballotpedia.org", "wikipedia.org")):
            if self._matches_canonical_slug(url, state, state_name, year, office):
                boost += 0.4
                reasons.append("canonical_slug_hit")

        # Construct overall decision
        match_strength = boost  # we already used boost for canonical; keep as report
        passed = (penalty < 0.3) and (state_hit or office_ok)

        summary = "ok" if passed else "fail"
        if reasons:
            summary += ":" + ",".join(reasons)

        return {
            "pass": passed,
            "reasons": reasons,
            "match_strength": min(0.5, match_strength),
            "penalty": min(0.4, penalty),
            "summary": summary,
        }

    def _office_match(self, office: str, combined_lower: str) -> bool:
        """Heuristic office matching for common offices."""
        if not office:
            return True
        if office in ("senate", "us-senate", "u.s.-senate", "ussenate", "us_senate"):
            return (
                ("u.s. senate" in combined_lower)
                or ("united states senate" in combined_lower)
                or ("us senate" in combined_lower)
            )
        if office in ("house", "us-house", "u.s.-house", "ushouse", "us_house"):
            return (
                ("u.s. house" in combined_lower)
                or ("united states house" in combined_lower)
                or ("house of representatives" in combined_lower)
            )
        if office in ("governor", "governorship", "gubernatorial"):
            return ("governor" in combined_lower) or ("gubernatorial" in combined_lower)
        # fallback: just check literal office token
        return office.replace("_", " ") in combined_lower

    def _detect_other_state_hit(self, combined_lower: str, current_state_abbr: str) -> Optional[str]:
        """Detect if another state's name/abbr appears prominently."""
        curr = current_state_abbr.upper()
        for abbr, name in self._STATE_MAP.items():
            if abbr == curr:
                continue
            name_l = name.lower()
            if f" {abbr.lower()} " in combined_lower or f" {name_l} " in combined_lower:
                return abbr
        return None

    def _matches_canonical_slug(self, url: str, state: str, state_name: Optional[str], year: int, office: str) -> bool:
        """Check if URL path looks like the canonical Ballotpedia/Wikipedia election page for the race."""
        try:
            parsed = urlparse(url)
            host = parsed.netloc.lower()
            path = parsed.path

            state_name = state_name or self._STATE_MAP.get(state.upper(), "")
            state_name_u = (state_name or "").replace(" ", "_")
            year_s = str(year)

            # Ballotpedia canonical pattern examples:
            # /United_States_Senate_election_in_Missouri,_2024
            # /United_States_House_of_Representatives_elections_in_Missouri,_2024
            if "ballotpedia.org" in host:
                if office in ("senate", "us-senate", "ussenate", "us_senate", "u.s.-senate"):
                    bp = rf"/United_States_Senate_election_in_{re.escape(state_name_u)},_{year_s}$"
                    return re.search(bp, path, flags=re.IGNORECASE) is not None
                if office in ("house", "us-house", "ushouse", "us_house", "u.s.-house"):
                    bp = rf"/United_States_House_of_Representatives_elections_in_{re.escape(state_name_u)},_{year_s}$"
                    return re.search(bp, path, flags=re.IGNORECASE) is not None
                if office in ("governor", "gubernatorial"):
                    bp = rf"/Gubernatorial_election_in_{re.escape(state_name_u)},_{year_s}$"
                    return re.search(bp, path, flags=re.IGNORECASE) is not None

            # Wikipedia canonical pattern examples:
            # /wiki/2024_United_States_Senate_election_in_Missouri
            # /wiki/2024_United_States_House_of_Representatives_elections_in_Missouri
            if "wikipedia.org" in host:
                if office in ("senate", "us-senate", "ussenate", "us_senate", "u.s.-senate"):
                    wp = rf"/wiki/{year_s}_United_States_Senate_election_in_{re.escape(state_name_u)}$"
                    return re.search(wp, path, flags=re.IGNORECASE) is not None
                if office in ("house", "us-house", "ushouse", "us_house", "u.s.-house"):
                    wp = rf"/wiki/{year_s}_United_States_House_of_Representatives_elections_in_{re.escape(state_name_u)}$"
                    return re.search(wp, path, flags=re.IGNORECASE) is not None
                if office in ("governor", "gubernatorial"):
                    wp = rf"/wiki/{year_s}_{re.escape(state_name_u)}_gubernatorial_election$"
                    return re.search(wp, path, flags=re.IGNORECASE) is not None

        except Exception:
            return False

        return False

    def _pick_issue(self, preferred: str = "GENERAL") -> CanonicalIssue:
        """Pick a valid CanonicalIssue, tolerating missing members."""
        if hasattr(CanonicalIssue, preferred):
            return getattr(CanonicalIssue, preferred)
        for alt in ("GENERAL_ELECTIONS", "DEFAULT"):
            if hasattr(CanonicalIssue, alt):
                return getattr(CanonicalIssue, alt)
        try:
            return next(iter(CanonicalIssue))
        except Exception as e:  # noqa: BLE001
            raise AttributeError("No usable CanonicalIssue enum member found") from e
