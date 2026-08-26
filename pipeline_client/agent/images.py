"""Image URL validation, accessibility checking, and candidate image resolution."""

import asyncio
import logging
import re
import unicodedata
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import unquote, urljoin, urlparse

import httpx

from .ballotpedia import lookup_candidate_image as _ballotpedia_lookup
from .run_budget import RunBudget, RunBudgetExceeded
from .utils import make_logger
from .web_tools import _serper_image_search

logger = logging.getLogger("pipeline")

_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg"})

_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_WIKIMEDIA_API_UA = "SmarterVoteBot/1.0 (https://smarter.vote; contact: dev@smarter.vote)"

_NON_PHOTO_TOKENS = frozenset(
    {
        "avatar",
        "badge",
        "background",
        "banner",
        "collage",
        "family",
        "favicon",
        "footerbg",
        "herobg",
        "homepage",
        "icon",
        "landscape",
        "logo",
        "mountain",
        "placeholder",
        "seal",
        "socialshare",
        "social-share",
        "sprite",
        "submit-photo",
        "submitphoto",
        "torch",
        "wordmark",
    }
)


class _PageImageParser(HTMLParser):
    """Collect image metadata from a candidate's known web page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: List[Tuple[str, str, int, int, str, int]] = []
        self._text_parts: List[str] = []
        self._text_len = 0
        self._open_tags: List[Tuple[str, bool]] = []
        self._widget_depth = 0

    @property
    def text(self) -> str:
        return "".join(self._text_parts)

    def handle_data(self, data: str) -> None:
        if not data:
            return
        self._text_parts.append(data)
        self._text_len += len(data)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        for position in range(len(self._open_tags) - 1, -1, -1):
            open_tag, is_widget = self._open_tags[position]
            if open_tag == name:
                if is_widget:
                    self._widget_depth = max(0, self._widget_depth - 1)
                del self._open_tags[position:]
                return

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        name = tag.lower()
        if name not in _VOID_HTML_TAGS:
            marker = f"{values.get('class', '')} {values.get('id', '')}".lower()
            is_widget = any(token in marker for token in _ROTATING_WIDGET_TOKENS)
            if is_widget:
                self._widget_depth += 1
            self._open_tags.append((name, is_widget))
        if tag.lower() == "meta":
            property_name = (values.get("property") or values.get("name") or "").lower()
            if property_name in {"og:image", "og:image:url", "og:image:secure_url", "twitter:image"}:
                self.images.append((values.get("content", ""), property_name, 0, 0, "", self._text_len))
            return
        if tag.lower() != "img":
            return

        source = values.get("data-image") or values.get("data-src") or values.get("src") or ""
        alt = values.get("alt") or values.get("title") or ""
        try:
            width = int(values.get("width", "0"))
            height = int(values.get("height", "0"))
        except ValueError:
            width = height = 0
        if self._widget_depth:
            # A rotating widget (Ballotpedia's Candidate Connection carousel,
            # a site slideshow) cycles through OTHER people's photos, so an
            # <img> inside one is not this candidate's portrait even though it
            # sits on their own page.  Nebraska's Senate race stored a survey
            # carousel slide of an unrelated candidate as Dan Osborn's photo.
            return
        self.images.append((source, "img", width, height, alt, self._text_len))


def _fold_accents(value: str) -> str:
    """Strip diacritics so accented names survive ASCII tokenization.

    Without this, "Peña" tokenizes as "pe" + "a" -- both below the length
    floor -- so the surname vanishes and every guard that compares names
    silently passes anything sharing the given name.  tx-house-37-2026 stored a
    1945 press photo of the actress Lauren Bacall for Lauren B. Peña that way.
    """
    return "".join(ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch))


def _name_tokens(candidate_name: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", _fold_accents(candidate_name).lower()) if len(token) >= 3}


def _candidate_surname_token(candidate_name: str) -> Optional[str]:
    """Return the candidate's surname (last name token, by naming convention), or None."""
    tokens = [t for t in re.findall(r"[a-zA-Z0-9]+", candidate_name) if len(t) >= 3]
    return tokens[-1].lower() if tokens else None


_WIKIMEDIA_NON_CANDIDATE_QUALIFIERS = frozenset(
    {"actor", "actress", "band", "composer", "director", "footballer", "musician", "singer"}
)


def _is_untrusted_wikimedia_match(url: str, candidate_name: str) -> bool:
    """True if an upload.wikimedia.org filename does not match the full name.

    Guards against the same fuzzy-match risk as Wikipedia's opensearch API
    (e.g. "Sam Mead" resolving to "Sam Mendes"), but for a URL that was
    already persisted onto the candidate from an earlier run rather than a
    fresh search result — the existing-URL fast path below would otherwise
    just re-validate it's still *accessible* without checking it's still the
    right person.
    """
    if "upload.wikimedia.org" not in url:
        return False
    candidate_tokens = _name_tokens(candidate_name)
    if not candidate_tokens:
        return False
    url_tokens = _name_tokens(unquote(url))
    return not candidate_tokens.issubset(url_tokens) or bool(url_tokens & _WIKIMEDIA_NON_CANDIDATE_QUALIFIERS)


# Words that appear in a Ballotpedia filename without being part of anybody's
# name, so they must not count toward "this file is named after a person".
_FILENAME_NON_NAME_TOKENS = frozenset(
    {
        "ballotpedia",
        "campaign",
        "candidate",
        "congress",
        "congressional",
        "copy",
        "crop",
        "cropped",
        "district",
        "final",
        "governor",
        "headshot",
        "house",
        "image",
        "img",
        "large",
        "new",
        "official",
        "photo",
        "picture",
        "portrait",
        "profile",
        "representative",
        "senate",
        "senator",
        "small",
        "square",
        "thumb",
        "thumbnail",
        "updated",
        "web",
        "rep",
        "sen",
        "gov",
    }
)


def _filename_person_tokens(url: str) -> List[str]:
    """Return name-like word tokens from an image filename.

    Splits on punctuation and on camelCase runs so "PeteRicketts2015" and
    "Audrey_Hatch_20240808_095600" both reduce to a first/last name pair.
    """
    basename = unquote(urlparse(url).path).rsplit("/", 1)[-1]
    basename = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", basename)
    words: List[str] = []
    for chunk in re.split(r"[^A-Za-z]+", basename):
        if not chunk:
            continue
        words.extend(re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", chunk))
    return [
        w.lower()
        for w in words
        # A name has a vowel.  Without this, hex runs inside a GUID filename
        # ("...46bdb6089bbb...") read as two name-like tokens and condemn the
        # photo.
        if len(w) >= 3 and w.lower() not in _FILENAME_NON_NAME_TOKENS and re.search(r"[aeiouy]", w, re.I)
    ]


_NAME_SUFFIX_TOKENS = frozenset({"jnr", "jr", "snr", "sr", "ii", "iii", "iv", "v", "vi"})


def _candidate_surname(candidate_name: str) -> Optional[str]:
    """Return the candidate's surname, ignoring a generational suffix."""
    tokens = [t.lower() for t in re.findall(r"[A-Za-z]+", _fold_accents(candidate_name))]
    tokens = [t for t in tokens if len(t) >= 2 and t not in _NAME_SUFFIX_TOKENS]
    return tokens[-1] if tokens else None


def _middle_initial(name: str) -> Optional[str]:
    """Return a lone middle initial from "Robert P. Murray", else None."""
    parts = re.findall(r"[A-Za-z]+", _fold_accents(name))
    if len(parts) < 3:
        return None
    middles = [p for p in parts[1:-1] if len(p) == 1]
    return middles[0].lower() if len(middles) == 1 else None


def _middle_initials_conflict(candidate_name: str, basename: str) -> bool:
    """True if the file names a namesake distinguished only by middle initial.

    va-house-04-2026 stored the Wikipedia portrait of Robert E. Murray -- the
    Murray Energy chief executive, who died in 2020 -- for the candidate
    Robert P. Murray.  Given and family names both matched, so only the middle
    initial separated a living candidate from a dead coal executive.

    The initial must stand alone as its own word in the filename.  Matching it
    inside a flattened string reads the "n" of "StevenParsons" as an initial
    and rejects Steve G. Parsons' own photo.
    """
    mine = _middle_initial(candidate_name)
    if not mine:
        return False
    name_parts = [p.lower() for p in re.findall(r"[A-Za-z]+", _fold_accents(candidate_name))]
    first, last = name_parts[0], name_parts[-1]
    words: List[str] = []
    for chunk in re.split(r"[^A-Za-z]+", _fold_accents(basename)):
        if chunk:
            words.extend(w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", chunk))
    for index, word in enumerate(words):
        if word != first or index + 2 >= len(words) + 1:
            continue
        rest = words[index + 1 :]
        if len(rest) >= 2 and len(rest[0]) == 1 and rest[1] == last:
            return rest[0] != mine
    return False


def _is_mismatched_person_filename(url: str, candidate_name: str) -> bool:
    """True if an image filename is named after a different person.

    Two separate failures motivate this.  Ballotpedia's own markup is not
    always right: on Dan Osborn's page the Nebraska Senate votebox rendered
    ``Audrey_Hatch_20240808_095600.jpg`` under ``alt="Image of Dan Osborn"``,
    so the page vouched for the wrong face.  And a Colorado candidate's photo
    was served from ``.../advisor/wayne.r.verity/wayne-verity_400x490.jpg`` —
    an Ameriprise adviser who merely shares a given name with Wayne Thornton.

    So when a filename spells out a full name, the *surname* has to be this
    candidate's; a shared first name is not enough.  Filenames that name
    nobody (``IMG-20260117-WA0002``, ``Carl4congress_profile``) are left alone
    because candidates upload those themselves.
    """
    # A conflicting middle initial is checked on every host, and before the
    # surname match below, because a namesake shares the surname.  It demands
    # an explicit initial on both sides, so a slogan filename cannot trip it.
    if _middle_initials_conflict(candidate_name, unquote(urlparse(url).path).rsplit("/", 1)[-1]):
        return True
    # Otherwise only Ballotpedia names its files after people by convention.
    # On an arbitrary campaign host a filename is as likely to be a slogan --
    # "GrahamforMaine_HeroPhoto.jpg" is Graham Platner's own hero image, and
    # his surname is nowhere in it.
    if "ballotpedia" not in url.lower():
        return False
    surname = _candidate_surname(candidate_name)
    if not surname:
        return False
    file_tokens = _filename_person_tokens(url)
    # One bare token is too weak a signal to overrule the page it came from.
    if len(file_tokens) < 2:
        return False
    # Compare against the letters-only filename, not just the split tokens: a
    # camelCase split fractures "McGuire" into Mc/Guire and drops the two-letter
    # fragment, which would otherwise condemn every Mc-, Mac-, De- and La- name
    # in the catalog.
    flattened = re.sub(r"[^a-z]", "", unquote(urlparse(url).path).rsplit("/", 1)[-1].lower())
    if surname in flattened:
        return False
    # Candidates upload descriptively named photos of themselves
    # ("Connie-Centered.png", "IlhanPortrait3.jpg", "meet-paige.jpg").  If the
    # file names this candidate at all, believe the page it came from.  Match
    # whole tokens here rather than substrings, so a short given name like
    # "Dan" cannot be satisfied by "Jordan".
    if _name_tokens(candidate_name).intersection(file_tokens):
        return False
    # Ballotpedia misspells names ("Tom_Periello" for Perriello, "Jessi_Eben"
    # for Ebben).  Those are still the right person, so allow a near miss --
    # but only for a surname long enough that proximity means something.
    if len(surname) >= 5 and any(_within_edit_distance(surname, token, 2) for token in file_tokens):
        return False
    return True


def _within_edit_distance(left: str, right: str, limit: int) -> bool:
    """True if `left` and `right` are at most `limit` single-character edits apart."""
    if abs(len(left) - len(right)) > limit:
        return False
    previous = list(range(len(right) + 1))
    for i, lch in enumerate(left, 1):
        current = [i]
        for j, rch in enumerate(right, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (lch != rch)))
        previous = current
    return previous[-1] <= limit


# Generic Open-Graph / social-share cards served by data and reference sites
# (e.g. https://www.fec.gov/static/img/social/fec-data.png) are never a
# candidate headshot even though they pass the extension check.
_GENERIC_CARD_MARKERS = (
    "/static/img/social",
    "/social/",
    "fec-data",
    "og-default",
    "default-og",
    "opengraph",
    "twitter-card",
    "sharecard",
    "share-card",
    "fb_share",
    "fb-share",
)

# Current candidates should never inherit portraits from obituary or memorial
# repositories.  Those URLs are often valid image files, so reachability alone
# cannot distinguish the common-name collision from a candidate headshot.
_MEMORIAL_IMAGE_MARKERS = (
    "/obituaries/",
    "/obituary/",
    "/deceased/",
    "/in-memoriam/",
    "findagrave",
    "funeralhome",
    "funeral-home",
    "legacy.com",
    "tributearchive",
    "dignitymemorial",
)

# Assets served out of a CMS theme/template directory *may* be site furniture —
# stock "VOTE" banners, masthead art, decorative headers — shipped with the
# website template rather than a photo of the candidate.  The directory alone
# is not enough to judge: WordPress campaign sites routinely serve the real
# headshot from wp-content/themes/<theme>/, so the filename must also read as
# furniture before the image is rejected.
_SITE_THEME_DIR_MARKERS = (
    "/templates/",
    "/template/",
    "/themes/",
    "/theme/",
)

# Campaign collateral published alongside a candidate's photos — policy
# one-pagers, agenda graphics, yard-sign art.  These are legitimate uploads in
# the site's own media directory, so no path marker separates them from a
# headshot; only the filename does.
# Licensed stock libraries.  Their watermarked comps are never a candidate
# portrait, they are usually a namesake or an unrelated stock model, and
# republishing one is a licensing problem on top of a factual one.  Twice this
# session a Getty archive photo was stored as a headshot: a 1947 picture of the
# jazz singer Mildred Bailey for a candidate named Mildred Hall (matched via
# "Carnegie HALL"), and a 1989 picture of the British astronaut candidates
# Helen Sharman and Timothy Mace for a candidate named Tim S. Sharman.
_STOCK_PHOTO_HOSTS = (
    "gettyimages.com",
    "gettyimages.co",
    "shutterstock.com",
    "alamy.com",
    "istockphoto.com",
    "dreamstime.com",
    "depositphotos.com",
    "stock.adobe.com",
    "123rf.com",
    "bigstockphoto.com",
)


# Retail product CDNs.  A surname that is also a common noun drags these in:
# mi-house-13-2026 stored a Home Depot pendant light fixture
# ("matte-black-rennnsan-pendant-lights-pl8101") as the headshot for a
# candidate named Raelyn Light, and the surname matched the filename.
_PRODUCT_IMAGE_HOSTS = (
    # Crowdfunding platforms serve campaign *graphics* -- a donate banner with
    # headline text, a QR code and the subject's face in one corner.
    # mi-house-10-2026 stored a GoFundMe banner advertising a candidate's book
    # as his headshot.
    "gofundme.com",
    "gofund.me",
    "kickstarter.com",
    "indiegogo.com",
    "givebutter.com",
    "thdstatic.com",
    "lowes.com",
    "walmartimages.com",
    "media-amazon.com",
    "ssl-images-amazon.com",
    "ebayimg.com",
    "wayfair.com",
    "etsystatic.com",
    "shopifycdn.com",
    "cdn.shopify.com",
    "scene7.com",
)


def _is_product_image(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if any(host == m or host.endswith("." + m) or m in host for m in _PRODUCT_IMAGE_HOSTS):
        return True
    return "/productimages/" in parsed.path.lower()


def _is_stock_photo_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == marker or host.endswith("." + marker) or marker in host for marker in _STOCK_PHOTO_HOSTS)


_CAMPAIGN_COLLATERAL_TOKENS = (
    "agenda",
    "brochure",
    "bumper",
    "button",
    "sticker",
    "flyer",
    "infographic",
    "priorities",
    "to-do",
    "todo",
    "yard-sign",
    "yardsign",
    "_plan_",
    "-plan-",
    "plan_for",
    "plan-for",
    "plan_fore",
    "plan-fore",
)

# Containers that rotate through several unrelated entries.  An <img> inside
# one belongs to whichever item the widget happens to show first, which is
# routinely a different person than the page is about.  Kept deliberately
# narrow: a plain "sidebar" or "related" block legitimately holds the infobox
# portrait on Ballotpedia and Wikipedia.
_ROTATING_WIDGET_TOKENS = (
    "carousel",
    "slideshow",
    "slick-",
    "swiper",
    "lightbox",
)

_VOID_HTML_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

_SITE_FURNITURE_TOKENS = (
    "header",
    "masthead",
    "footer",
    "nav",
    "hero",
    "slider",
    "slideshow",
    "carousel",
    "divider",
    "watermark",
)


# A CMS's auto-generated filename for an image saved from somewhere else
# ("download-83.png", "unnamed.jpg", "img_1024.jpeg").  On a news site these
# are usually article art — a composite of several people, a graphic, a scene
# — never a portrait tied to one candidate.  Matched on the filename stem
# alone so a "/downloads/" directory or a candidate actually named e.g.
# "Imogen" is unaffected, and so dated capture names like the
# "screenshot-2026-07-30-154741.png" used by newsroom questionnaires still pass.
_GENERIC_CMS_FILENAME_RE = re.compile(r"^(?:download|unnamed|untitled|image|img|photo|picture|file|default)[-_ ]?\d*$")


def _looks_like_generic_cms_filename(url: str) -> bool:
    """True when the filename carries no identity, only a CMS auto-name."""
    try:
        path = unquote(urlparse(url).path)
    except Exception:
        return False
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].strip().lower()
    if not stem:
        return False
    return bool(_GENERIC_CMS_FILENAME_RE.match(stem))


def _looks_like_site_furniture(haystack: str) -> bool:
    """True for template art (a stock banner), not a portrait stored in a theme."""
    if not any(marker in haystack for marker in _SITE_THEME_DIR_MARKERS):
        return False
    return any(token in haystack for token in _SITE_FURNITURE_TOKENS)


def _contains_word(haystack: str, token: str) -> bool:
    """True if `token` appears in `haystack` other than inside a longer word.

    A plain substring test reads "icon" inside "NikiConforti", "banner" inside
    "Bannerman" and "seal" inside "Seale", condemning those candidates' own
    photos.  What separates those from a real hit is the character that
    *follows*: a lowercase letter means the token is a fragment of a longer
    word.  Names run on before the token often enough
    ("halliewebsiteshoffnerhomepage.png") that the preceding character cannot
    be required to be a boundary.  A plural "s" still counts as the end of the
    word, so "creamlogos3.png" matches while "Logothetis.jpg" does not.
    """

    def _boundary(index: int) -> bool:
        if index >= len(haystack):
            return True
        char = haystack[index]
        if not (char.isalpha() and char.islower()):
            return True
        return char == "s" and not (
            index + 1 < len(haystack) and haystack[index + 1].isalpha() and haystack[index + 1].islower()
        )

    return any(_boundary(m.end()) for m in re.finditer(re.escape(token), haystack, re.IGNORECASE))


def _looks_like_non_photo(url: str, alt: str = "") -> bool:
    haystack = unquote(f"{url} {alt}").lower()
    # Some CMSes join words with "+" ("Social+Share+Card"), so test a variant
    # with separators unified to "-" as well.
    unified = re.sub(r"[+_\s]+", "-", haystack)
    if any(_contains_word(haystack, token) or _contains_word(unified, token) for token in _NON_PHOTO_TOKENS):
        return True
    if any(marker in haystack for marker in (*_GENERIC_CARD_MARKERS, *_MEMORIAL_IMAGE_MARKERS)):
        return True
    if any(token in haystack for token in _CAMPAIGN_COLLATERAL_TOKENS):
        return True
    if _looks_like_generic_cms_filename(url):
        return True
    if _is_stock_photo_host(url) or _is_product_image(url):
        return True
    if _looks_like_archival_photo(url):
        return True
    if _looks_like_social_card(url):
        return True
    if _looks_like_banner_crop(url):
        return True
    if _is_wikimedia_occupational_namesake(url):
        return True
    if _looks_like_endorsement_badge(url):
        return True
    return _looks_like_site_furniture(haystack)


_SOCIAL_CARD_PATTERN = re.compile(
    r"(?:^|[-_.])(?:og[-_]?image|opengraph|social[-_](?:card|share|image)|twitter[-_]card)(?:[-_.]|$)"
)


_SOCIAL_CARD_PATH_PATTERN = re.compile(r"/(?:og|opengraph|social[-_]?card|social[-_]?share)/")


def _looks_like_social_card(url: str) -> bool:
    """True for the Open Graph preview image a site advertises a candidate with.

    These live on the candidate's own domain — normally the most trustworthy
    source — but they are branding, not portraits: CO-06 stored a "RESPECT /
    RESTORE / REFORM" banner as Samir Witta's headshot, and NY-26 a card that
    is mostly the words "DENNIS HANNON FOR CONGRESS".

    Card *generators* name the file after the candidate and put the giveaway in
    the path instead, so both are checked: "linktr.ee/og/image/
    wingfieldforcongress.jpg" is a Linktree card, and "themidtermproject.org/
    api/og/candidate/barnett-shafina.png" renders the initials "SB" on a tile
    where the photograph would be.
    """
    path = unquote(urlparse(url).path).lower()
    if _SOCIAL_CARD_PATH_PATTERN.search(path):
        return True
    return bool(_SOCIAL_CARD_PATTERN.search(path.rsplit("/", 1)[-1]))


_BANNER_DIMENSIONS_PATTERN = re.compile(r"(?:^|[-_])(\d{2,5})x(\d{2,5})(?:[-_.]|$)")


def _looks_like_banner_crop(url: str) -> bool:
    """True when the filename's own dimensions describe a banner, not a portrait.

    A CMS records the crop it produced, so "WebsiteUpdate2-1920x860.jpg" is a
    page-wide hero strip — CA-44 stored one, a press conference in front of the
    Capitol, as Nanette Barragan's headshot.  No portrait is twice as wide as
    it is tall.
    """
    basename = unquote(urlparse(url).path).rsplit("/", 1)[-1].lower()
    match = _BANNER_DIMENSIONS_PATTERN.search(basename)
    if not match:
        return False
    width, height = int(match.group(1)), int(match.group(2))
    return bool(height) and width / height >= 2.0


# A parenthetical on a Wikimedia file is how MediaWiki disambiguates a name.
# These qualifiers describe the file, or a politician, so they are not evidence
# of a namesake.
_WIKIMEDIA_SAFE_QUALIFIERS = frozenset(
    {
        "attorney",
        "congress",
        "congressional",
        "congressman",
        "congresswoman",
        "crop",
        "cropped",
        "governor",
        "headshot",
        "house",
        "judge",
        "mayor",
        "official",
        "photo",
        "politician",
        "portrait",
        "representative",
        "resized",
        "retouched",
        "scaled",
        "senate",
        "senator",
        "uncropped",
    }
)

_US_STATE_WORDS = frozenset(
    {
        "alabama",
        "alaska",
        "arizona",
        "arkansas",
        "california",
        "carolina",
        "colorado",
        "connecticut",
        "dakota",
        "delaware",
        "florida",
        "georgia",
        "hampshire",
        "hawaii",
        "idaho",
        "illinois",
        "indiana",
        "iowa",
        "island",
        "jersey",
        "kansas",
        "kentucky",
        "louisiana",
        "maine",
        "maryland",
        "massachusetts",
        "mexico",
        "michigan",
        "minnesota",
        "mississippi",
        "missouri",
        "montana",
        "nebraska",
        "nevada",
        "ohio",
        "oklahoma",
        "oregon",
        "pennsylvania",
        "rhode",
        "tennessee",
        "texas",
        "utah",
        "vermont",
        "virginia",
        "washington",
        "wisconsin",
        "wyoming",
        "york",
    }
)

_PARTY_STATE_TAG = re.compile(r"^[rdi]-[a-z]{2}$")


def _is_wikimedia_occupational_namesake(url: str) -> bool:
    """True for a Wikimedia portrait disambiguated to somebody else's occupation.

    A shared surname defeats every name check, so the qualifier MediaWiki adds
    to break the tie is the only signal that the file is a different person:
    "Eric_Jones_(solo_climber)" was a British mountaineer stored for a CA-04
    candidate, "Ryan_Kelly_(American_football)" a Colts lineman, and
    "James_Burke_(science_historian)" the television presenter.

    Qualifiers carrying a digit ("(119th Congress)", "(1)", "(3x4)", Flickr
    ids), a party-state tag ("(R-TN)"), or a political/file word are how
    genuine official portraits are named, so they are left alone.
    """
    if urlparse(url).netloc.lower() not in {"upload.wikimedia.org", "commons.wikimedia.org"}:
        return False
    basename = unquote(urlparse(url).path).rsplit("/", 1)[-1].lower()
    for match in re.finditer(r"\(([^)]*)\)", basename):
        inner = match.group(1).strip()
        if any(character.isdigit() for character in inner):
            continue
        if _PARTY_STATE_TAG.match(inner):
            continue
        words = set(re.findall(r"[a-z]+", inner))
        if not words or words & _WIKIMEDIA_SAFE_QUALIFIERS or words & _US_STATE_WORDS:
            continue
        return True
    return False


_ENDORSEMENT_BADGE_PATTERNS = (
    # "CAGOP ENDORSED CANDIDATE" seals, and the party-organisation variants of
    # them, are hosted on the candidate's own site alongside real portraits.
    re.compile(r"(?:^|[-_])[a-z]{2}(?:gop|dems?|dp|rp)[-_](?:endorsed|candidate)(?:[-_.]|$)"),
    re.compile(r"(?:^|[-_])(?:endorsed|endorsement)(?:[-_.]|$)"),
)


def _looks_like_endorsement_badge(url: str) -> bool:
    """True for party endorsement seals, which carry a logo rather than a face.

    A candidate's own campaign site is normally the most trustworthy source for
    a headshot, so these graphics slip past every host-based check: CA-38 stored
    a green "CAGOP ENDORSED CANDIDATE" rosette from ``casasforcongress.com`` as
    Pedro Casas' portrait.  The badge names a designation, never a person.
    """
    basename = unquote(urlparse(url).path).rsplit("/", 1)[-1].lower()
    return any(pattern.search(basename) for pattern in _ENDORSEMENT_BADGE_PATTERNS)


def _looks_like_archival_photo(url: str) -> bool:
    """True if the filename dates the image to before any current candidate's career.

    A historical namesake is a recurring failure: a 19th-century preacher was
    stored for Henry Ward III, and a 1945 press photo of the actress Lauren
    Bacall for Lauren B. Pena.  A pre-1980 year in the filename is archive
    provenance, never a current campaign portrait.
    """
    basename = unquote(urlparse(url).path).rsplit("/", 1)[-1]
    # "-1920w" and "1920x1000" are responsive-image dimensions, not years.
    years = re.findall(r"(?<![\dxX])(1[89]\d{2})(?![\dwhxWHX])", basename)
    return any(1800 <= int(year) <= 1979 for year in years)


def _looks_like_social_profile_avatar(url: str) -> bool:
    """Return True for small social-network profile avatars worth upgrading.

    A Twitter/X profile image is frequently not a usable candidate portrait —
    it may be a logo, a family snapshot, or a face obscured by sunglasses and a
    mask — and it is served at avatar resolution.  It stays usable as a last
    resort, but a photo published on the candidate's own site or in a local
    newsroom's candidate questionnaire should outrank it.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.netloc.lower() == "pbs.twimg.com" and "/profile_images/" in unquote(parsed.path).lower()


def _looks_like_govtrack_reference_headshot(url: str) -> bool:
    """Return True for GovTrack's small legislator headshots worth upgrading."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    netloc = parsed.netloc.lower()
    path = unquote(parsed.path).lower()
    return netloc == "www.govtrack.us" and "/static/legislator-photos/" in path


# Character distances between an image and a mention of the candidate's name in
# the page's extracted text.  A questionnaire entry (photo, name, answers) sits
# well inside the "near" window; the "far" window still favours the right half
# of a two-candidate page over a shared article hero.
_NAME_PROXIMITY_NEAR = 1200
_NAME_PROXIMITY_FAR = 4000


def _name_text_offsets(text: str, candidate_name: str) -> List[int]:
    """Return offsets where the candidate's full name appears in page text."""
    tokens = [token for token in re.findall(r"[A-Za-z0-9]+", candidate_name) if len(token) >= 3]
    if len(tokens) < 2:
        return []
    pattern = r"\b" + r"\W+(?:\w+\W+){0,2}?".join(re.escape(token) for token in tokens) + r"\b"
    try:
        return [match.start() for match in re.finditer(pattern, text, re.IGNORECASE)]
    except re.error:
        return []


def _extract_page_image_urls(html: str, page_url: str, candidate_name: str) -> List[str]:
    """Return candidate page images ordered from most to least likely portrait."""
    parser = _PageImageParser()
    parser.feed(html)
    name_tokens = _name_tokens(candidate_name)
    name_offsets = _name_text_offsets(parser.text, candidate_name)
    ranked: List[Tuple[int, int, int, str]] = []
    seen: set[str] = set()

    for index, (raw_url, source, width, height, alt, text_offset) in enumerate(parser.images):
        if not raw_url:
            continue
        url = urljoin(page_url, raw_url)
        if url.startswith("http://"):
            url = f"https://{url[7:]}"
        if url in seen or not _is_valid_image_url(url) or _looks_like_non_photo(url, alt):
            continue
        if _is_mismatched_person_filename(url, candidate_name):
            continue
        seen.add(url)

        searchable = unquote(f"{url} {alt}").lower()
        score = (
            50 if source == "og:image" else 45 if source.startswith("og:image") else 35 if source == "twitter:image" else 20
        )
        score += 25 * len(name_tokens.intersection(re.findall(r"[a-z0-9]+", searchable)))
        if "photo" in searchable or "headshot" in searchable or "portrait" in searchable:
            score += 15
        if width >= 600 and height >= 600:
            score += 20
        elif width >= 300 and height >= 300:
            score += 10
        if source == "img" and width and height and width / max(height, 1) > 3:
            score -= 20
        # A candidate questionnaire or voter guide covers several people on one
        # page, and its og:image is a shared article hero that would otherwise
        # win for every candidate.  Prefer the image printed beside this
        # candidate's own name.
        distance = 0
        if name_offsets:
            distance = min(abs(offset - text_offset) for offset in name_offsets)
            if distance <= _NAME_PROXIMITY_NEAR:
                score += 60
            elif distance <= _NAME_PROXIMITY_FAR:
                score += 25
        # Within the same bucket the image printed closest to this candidate's
        # name wins, so adjacent entries in one voter guide stay distinct.
        ranked.append((score, -distance, -index, url))

    ranked.sort(reverse=True)
    return [url for _, _, _, url in ranked]


# Data / reference / finance sites never host a personal headshot on their
# pages — their Open-Graph image is a generic site card — so skip them when
# crawling candidate pages for a photo (Ballotpedia is handled via its own API).
# Local-newsroom pages that profile the field candidate-by-candidate.  These are
# often the only published photo of a third-party or write-in candidate, and the
# URL/title shape is a reliable signal that the page is a per-candidate profile
# rather than general campaign coverage.
_CANDIDATE_PROFILE_MARKERS = (
    "meet-the-candidates",
    "meet the candidates",
    "candidate-questionnaire",
    "questionnaire",
    "voter-guide",
    "voter guide",
    "candidate-profile",
    "who-is-running",
)

_NON_HEADSHOT_HOSTS = (
    # A financial-adviser profile CDN: co-house-04-2026 stored
    # ".../advisor/wayne.r.verity/wayne-verity_400x490.jpg" for Wayne
    # Thornton, an unrelated Ameriprise adviser sharing only a given name.
    "ameriprisecontent.com",
    "fec.gov",
    "opensecrets.org",
    "followthemoney.org",
    "ballotpedia.org",
    "votesmart.org",
    "congress.gov",
    "govtrack.us",
)


def _candidate_page_urls(candidate: Dict[str, Any]) -> List[str]:
    """Return known candidate pages, preferring candidate-specific profile URLs."""
    name_tokens = _name_tokens(str(candidate.get("name", "")))
    pages: List[Tuple[int, str]] = []
    website = candidate.get("website")
    if isinstance(website, str) and website.startswith(("http://", "https://")):
        pages.append((20, website))

    for link in candidate.get("links", []):
        if not isinstance(link, dict):
            continue
        url = link.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        if any(host in urlparse(url).netloc.lower() for host in _NON_HEADSHOT_HOSTS):
            continue
        parsed_path = unquote(urlparse(url).path).lower()
        score = 10
        if link.get("type") == "official" and parsed_path.strip("/"):
            score += 20
        if "/candidate/" in parsed_path or name_tokens.intersection(re.findall(r"[a-z0-9]+", parsed_path)):
            score += 30
        pages.append((score, url))

    for source in candidate.get("summary_sources", []):
        if not isinstance(source, dict):
            continue
        url = source.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        if any(host in urlparse(url).netloc.lower() for host in _NON_HEADSHOT_HOSTS):
            continue
        haystack = f"{unquote(urlparse(url).path)} {source.get('title') or ''}".lower()
        if not any(marker in haystack for marker in _CANDIDATE_PROFILE_MARKERS):
            continue
        pages.append((25, url))

    deduped: List[str] = []
    seen: set[str] = set()
    for _, url in sorted(pages, key=lambda item: item[0], reverse=True):
        normalized = url.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(url)
    return deduped[:8]


async def _lookup_known_page_image(candidate: Dict[str, Any]) -> Optional[str]:
    """Extract a direct image URL from known candidate website/profile pages."""
    headers = {"User-Agent": _BROWSER_UA}
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            for page_url in _candidate_page_urls(candidate):
                try:
                    response = await client.get(page_url, headers=headers)
                    response.raise_for_status()
                except Exception:
                    continue
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type.lower():
                    continue
                for image_url in _extract_page_image_urls(response.text, str(response.url), candidate.get("name", "")):
                    accessible, final_url = await _check_url_accessible(image_url)
                    if accessible:
                        store_url = final_url if _is_valid_image_url(final_url) else image_url
                        if _looks_like_govtrack_reference_headshot(store_url):
                            continue
                        return store_url
    except Exception as exc:
        logger.debug("Candidate page image lookup failed: %s", exc)
    return None


def _is_valid_image_url(url: Any) -> bool:
    """Return True only if the URL looks like a direct image file, not a web page.

    Deliberately strict: only accepts URLs with known image extensions or from
    image-serving hosts. Rejects commons.wikimedia.org/wiki/File: page URLs even
    though they contain 'wikimedia.org' — only upload.wikimedia.org serves files.
    """
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return False
    try:
        parsed = urlparse(url)
        path = parsed.path.lower()
        netloc = parsed.netloc.lower()

        # File extension check (most reliable signal)
        if any(path.rstrip("/").endswith(ext) for ext in _IMAGE_EXTENSIONS):
            return True

        # upload.wikimedia.org always serves image files directly.
        # Do NOT accept commons.wikimedia.org (file pages) or en.wikipedia.org (articles).
        if netloc == "upload.wikimedia.org":
            return True

        # Ballotpedia stores images under /wiki/images/
        if "ballotpedia.org" in netloc and "/wiki/images/" in path:
            return True

        # Common image CDNs
        if any(
            host in netloc
            for host in ("cloudfront.net", "githubusercontent.com", "twimg.com", "fbcdn.net", "brightspotcdn.com")
        ):
            return True

    except Exception:
        return False
    return False


async def _check_url_accessible(url: str) -> Tuple[bool, str]:
    """Check whether a URL is accessible, returning (accessible, final_url).

    Follows redirects and returns the final URL, which may differ from the input
    — useful for resolving Wikimedia Special:FilePath redirects to upload URLs.

    Strategy:
    1. HEAD with browser UA — fast, most servers support it.
    2. If HEAD returns 405/501, fall back to byte-range GET.
    """
    headers = {"User-Agent": _BROWSER_UA}
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.head(url, headers=headers)
            final_url = str(resp.url)
            if resp.status_code < 400:
                return True, final_url
            if resp.status_code in (405, 501):
                resp2 = await client.get(url, headers={**headers, "Range": "bytes=0-0"})
                return resp2.status_code in (200, 206), str(resp2.url)
            return False, url
    except Exception:
        return False, url


def _wikimedia_original_image_url(url: str) -> Optional[str]:
    """Return the original Wikimedia upload URL for thumbnail URLs."""
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.netloc.lower() != "upload.wikimedia.org":
        return None
    parts = parsed.path.split("/")
    try:
        thumb_index = parts.index("thumb")
    except ValueError:
        return None
    if thumb_index < 2 or len(parts) <= thumb_index + 3:
        return None
    original_parts = parts[:thumb_index] + parts[thumb_index + 1 : -1]
    if not original_parts or not original_parts[-1]:
        return None
    return parsed._replace(path="/".join(original_parts), query="", fragment="").geturl()


async def _best_accessible_image_url(url: str) -> Optional[str]:
    """Return the best accessible direct URL for an image candidate."""
    candidates: List[str] = []
    original = _wikimedia_original_image_url(url)
    if original:
        candidates.append(original)
    candidates.append(url)

    seen: set[str] = set()
    for candidate_url in candidates:
        if candidate_url in seen or not _is_valid_image_url(candidate_url):
            continue
        seen.add(candidate_url)
        accessible, final_url = await _check_url_accessible(candidate_url)
        if accessible:
            return final_url if _is_valid_image_url(final_url) else candidate_url
    return None


async def _lookup_wikipedia_image(candidate_name: str, context: str = "") -> Optional[str]:
    """Query the Wikipedia API to get a candidate's headshot URL.

    Uses opensearch to find the best matching page, then pageimages to get the
    image. Returns a direct upload.wikimedia.org URL, or None if not found.

    If ``context`` is provided (e.g. "Senator Arkansas Republican") it is
    appended to a second search pass so that a common name like "Mike Johnson"
    can be disambiguated when the bare-name search returns no thumbnail.
    """
    # opensearch is a fuzzy/autocomplete match, not an exact lookup — for a name
    # with no Wikipedia page (common for down-ballot candidates) it can return a
    # similarly-spelled but unrelated person (e.g. "Sam Mead" -> "Sam Mendes").
    # Require the candidate's full normalized name to appear in the matched
    # title before trusting its image. Surname-only matching accepted unrelated
    # entities such as "Dave Matthews Band" for candidate David Matthews.
    candidate_tokens = _name_tokens(candidate_name)

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:

            async def _search_and_fetch(query: str) -> Optional[str]:
                search_resp = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "opensearch",
                        "search": query,
                        "limit": "3",
                        "format": "json",
                    },
                    headers={"User-Agent": _WIKIMEDIA_API_UA},
                )
                search_resp.raise_for_status()
                search_data = search_resp.json()
                titles = search_data[1] if len(search_data) > 1 else []
                for title in titles:
                    if candidate_tokens and not candidate_tokens.issubset(_name_tokens(title)):
                        logger.debug(
                            "Rejected Wikipedia match %r for candidate %r — full name not present", title, candidate_name
                        )
                        continue
                    img_resp = await client.get(
                        "https://en.wikipedia.org/w/api.php",
                        params={
                            "action": "query",
                            "titles": title,
                            "prop": "pageimages",
                            "pithumbsize": "1000",
                            "format": "json",
                            "redirects": "1",
                        },
                        headers={"User-Agent": _WIKIMEDIA_API_UA},
                    )
                    img_resp.raise_for_status()
                    data = img_resp.json()
                    for page in data.get("query", {}).get("pages", {}).values():
                        thumb = page.get("thumbnail", {}).get("source", "")
                        resolved_title = str(page.get("title") or title)
                        if candidate_tokens and (
                            not candidate_tokens.issubset(_name_tokens(resolved_title))
                            or _name_tokens(resolved_title) & _WIKIMEDIA_NON_CANDIDATE_QUALIFIERS
                        ):
                            logger.debug(
                                "Rejected resolved Wikipedia title %r for candidate %r", resolved_title, candidate_name
                            )
                            continue
                        if (
                            thumb
                            and urlparse(thumb).netloc.casefold() == "upload.wikimedia.org"
                            and not _is_untrusted_wikimedia_match(thumb, candidate_name)
                        ):
                            return thumb
                return None

            # First pass: bare name search
            result = await _search_and_fetch(candidate_name)
            if result:
                return result

            # Second pass: name + context to disambiguate (e.g. common names)
            if context:
                result = await _search_and_fetch(f"{candidate_name} {context}")
                if result:
                    return result

    except Exception as e:
        logger.debug("Candidate image lookup failed: %s", e)
    return None


async def _lookup_ballotpedia_image(candidate_name: str) -> Optional[str]:
    """Return a Ballotpedia thumbnail URL for *candidate_name*, or None.

    Delegates to the shared :mod:`.ballotpedia` module so all Ballotpedia API
    logic lives in one place.
    """
    image_url = await _ballotpedia_lookup(candidate_name)
    if image_url and _looks_like_non_photo(image_url):
        return None
    return image_url


async def _resolve_wikimedia_commons(url: str) -> Optional[str]:
    """Convert a commons.wikimedia.org/wiki/File: URL to a direct upload URL.

    Uses the Special:FilePath redirect endpoint which always resolves to the
    canonical upload.wikimedia.org URL. Returns the upload URL, or None on failure.
    """
    if "commons.wikimedia.org/wiki/File:" not in url:
        return None
    filename = url.split("/wiki/File:", 1)[1]
    special_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{filename}"
    accessible, final_url = await _check_url_accessible(special_url)
    if accessible and "upload.wikimedia.org" in final_url:
        return final_url
    return None


async def _lookup_serper_image(
    candidate_name: str, context: Optional[str] = None, run_budget: RunBudget | None = None
) -> Optional[str]:
    """Search for a candidate headshot via Serper Images, ranked by relevance.

    Runs a few query variants, scores each result by how strongly its title/source
    references the candidate (to avoid generic party graphics or the wrong person),
    prefers portrait-shaped images, then returns the best accessible one.
    """
    name_tokens = _name_tokens(candidate_name)
    queries: List[str] = []
    if context:
        queries.append(f"{candidate_name} {context} headshot")
    queries.append(f"{candidate_name} candidate portrait")
    queries.append(candidate_name)

    scored: List[Tuple[int, str]] = []
    seen: set[str] = set()
    try:
        for query in queries:
            results = await _serper_image_search(query, num_results=10, run_budget=run_budget)
            for r in results:
                if not isinstance(r, dict):
                    continue
                img_url = r.get("imageUrl")
                if not isinstance(img_url, str) or img_url in seen:
                    continue
                seen.add(img_url)
                meta = f"{r.get('title', '')} {r.get('source', '')} {r.get('link', '') or r.get('domain', '')}"
                if not _is_valid_image_url(img_url) or _looks_like_non_photo(img_url, meta):
                    continue
                meta_tokens = set(re.findall(r"[a-z0-9]+", meta.lower()))
                overlap = len(name_tokens & meta_tokens)
                score = overlap * 10
                try:
                    width = int(r.get("imageWidth") or 0)
                    height = int(r.get("imageHeight") or 0)
                except (TypeError, ValueError):
                    width = height = 0
                if width and height:
                    ratio = width / max(height, 1)
                    if 0.6 <= ratio <= 1.4:  # portrait/square headshot shape
                        score += 4
                    elif ratio > 2.5 or ratio < 0.35:  # banner / sliver
                        score -= 6
                    if width < 200 or height < 200:
                        score -= 4
                scored.append((score, img_url))
            # A result whose title/source names the candidate is a strong hit; stop early.
            if any(s >= 10 for s, _ in scored):
                break

        for _, img_url in sorted(scored, key=lambda item: item[0], reverse=True):
            accessible, final_url = await _check_url_accessible(img_url)
            if accessible:
                return final_url if _is_valid_image_url(final_url) else img_url
    except Exception as e:
        logger.debug("Serper image fast path failed: %s", e)
    return None


# News outlets are named after the state they cover, so one covering a
# *different* state is reporting on a different person.  tn-house-07-2026
# stored media.newjerseyglobe.com's 2021 photo of a Mercer County, New Jersey
# commissioner named Andrew Koontz for the Tennessee candidate of that name.
# Only full state names are matched: two-letter abbreviations collide with
# ordinary words ("la" inside "lailluminator.com").  Longest first, so
# "westvirginia" is not read as "virginia".
_STATE_NAMES_BY_CODE = {
    "al": "alabama",
    "ak": "alaska",
    "az": "arizona",
    "ar": "arkansas",
    "ca": "california",
    "co": "colorado",
    "ct": "connecticut",
    "de": "delaware",
    "fl": "florida",
    "ga": "georgia",
    "hi": "hawaii",
    "id": "idaho",
    "il": "illinois",
    "in": "indiana",
    "ia": "iowa",
    "ks": "kansas",
    "ky": "kentucky",
    "la": "louisiana",
    "me": "maine",
    "md": "maryland",
    "ma": "massachusetts",
    "mi": "michigan",
    "mn": "minnesota",
    "ms": "mississippi",
    "mo": "missouri",
    "mt": "montana",
    "ne": "nebraska",
    "nv": "nevada",
    "nh": "newhampshire",
    "nj": "newjersey",
    "nm": "newmexico",
    "ny": "newyork",
    "nc": "northcarolina",
    "nd": "northdakota",
    "oh": "ohio",
    "ok": "oklahoma",
    "or": "oregon",
    "pa": "pennsylvania",
    "ri": "rhodeisland",
    "sc": "southcarolina",
    "sd": "southdakota",
    "tn": "tennessee",
    "tx": "texas",
    "ut": "utah",
    "vt": "vermont",
    "va": "virginia",
    "wa": "washington",
    "wv": "westvirginia",
    "wi": "wisconsin",
    "wy": "wyoming",
}
_STATE_NAMES_LONGEST_FIRST = sorted(set(_STATE_NAMES_BY_CODE.values()), key=len, reverse=True)


def _host_names_another_state(url: str, race_id: Optional[str]) -> bool:
    """True if the image host is named for a state other than the race's."""
    if not race_id:
        return False
    own = _STATE_NAMES_BY_CODE.get(race_id.split("-", 1)[0].lower())
    if not own:
        return False
    # Only the registrable domain: a CDN encodes its data-centre region in a
    # subdomain, and "bloximages.newyork1.vip.townnews.com" is TownNews'
    # infrastructure serving a Florida paper, not a New York outlet.
    labels = (urlparse(url).hostname or "").lower().split(".")
    host = re.sub(r"[^a-z]", "", "".join(labels[-2:]))
    for state in _STATE_NAMES_LONGEST_FIRST:
        if state in host:
            return state != own
    return False


async def _resolve_single_image(
    candidate: Dict[str, Any],
    *,
    agent_loop_fn: Callable,
    model: str,
    on_log: Optional[Callable] = None,
    race_id: Optional[str] = None,
    max_iterations: int = 10,
    office: str = "",
    jurisdiction: str = "",
    run_budget: RunBudget | None = None,
) -> None:
    """Validate and resolve image_url for a single candidate in-place."""
    log = make_logger(on_log)
    name = candidate.get("name", "unknown")
    current_url = candidate.get("image_url") or None  # Treat "" and None identically
    low_resolution_fallback: Optional[str] = None

    # Normalise empty string to None
    if not current_url:
        candidate["image_url"] = None

    if current_url and _looks_like_govtrack_reference_headshot(current_url):
        low_resolution_fallback = current_url
        candidate["image_url"] = None
        current_url = None
        log("info", f"  [{name}] Existing image is a low-resolution reference photo - searching for better")

    if current_url and _looks_like_social_profile_avatar(current_url):
        low_resolution_fallback = current_url
        candidate["image_url"] = None
        current_url = None
        log("info", f"  [{name}] Existing image is a social profile avatar - searching for a better portrait")

    if current_url and _host_names_another_state(current_url, race_id):
        log(
            "info",
            f"  [{name}] Existing image is hosted by another state's outlet - discarding and re-searching",
        )
        candidate["image_url"] = None
        current_url = None

    if current_url and _is_mismatched_person_filename(current_url, name):
        log(
            "info",
            f"  [{name}] Existing Ballotpedia image is filed under another person's name - discarding and re-searching",
        )
        candidate["image_url"] = None
        current_url = None

    if current_url and _is_untrusted_wikimedia_match(current_url, name):
        log(
            "info",
            f"  [{name}] Existing Wikimedia image's filename doesn't match this candidate's surname - discarding and re-searching",
        )
        candidate["image_url"] = None
        current_url = None

    # Commons file-page URL: resolve via Special:FilePath redirect
    if current_url and "commons.wikimedia.org/wiki/File:" in current_url:
        log("info", f"  [{name}] Commons page URL detected — resolving via Special:FilePath")
        direct = await _resolve_wikimedia_commons(current_url)
        if direct:
            candidate["image_url"] = direct
            log("info", f"  [{name}] Commons resolved → {direct[:80]}")
            return
        log("info", f"  [{name}] Commons resolution failed — will search for replacement")
        candidate["image_url"] = None
        current_url = None

    # Validate existing URL (extension / host check + live HEAD request)
    if current_url:
        if _is_valid_image_url(current_url) and not _looks_like_non_photo(current_url):
            log("info", f"  [{name}] Checking URL accessibility: {current_url[:80]}")
            best_url = await _best_accessible_image_url(current_url)
            if best_url:
                candidate["image_url"] = best_url
                if best_url != current_url:
                    log("info", f"  [{name}] URL upgraded to better form: {best_url[:80]}")
                else:
                    log("info", f"  [{name}] URL OK - keeping existing image")
                return
            accessible, final_url = await _check_url_accessible(current_url)
            if accessible:
                if final_url != current_url and _is_valid_image_url(final_url):
                    candidate["image_url"] = final_url
                    log("info", f"  [{name}] URL redirected to better form → {final_url[:80]}")
                else:
                    log("info", f"  [{name}] URL OK — keeping existing image")
                return
            log("info", f"  [{name}] URL is dead (HTTP error or timeout) — searching for replacement")
        else:
            log("info", f"  [{name}] URL failed validation (not a direct image file): {current_url[:80]}")
        candidate["image_url"] = None

    else:
        log("info", f"  [{name}] No image URL — starting search")

    # Build a context string from available race/candidate metadata to help
    # disambiguate common names (e.g. "Mike Johnson" → "Mike Johnson Senator Louisiana")
    context_parts = [p for p in (jurisdiction, office) if p]
    search_context = " ".join(context_parts)

    # Fast path 1: Ballotpedia API (politics-specific, no name-collision risk)
    log("info", f"  [{name}] Trying Ballotpedia API lookup...")
    bp_url = await _lookup_ballotpedia_image(name)
    if bp_url:
        log("info", f"  [{name}] Ballotpedia API returned: {bp_url[:80]}")
        accessible, final_url = await _check_url_accessible(bp_url)
        if accessible:
            store_url = final_url if _is_valid_image_url(final_url) else bp_url
            candidate["image_url"] = store_url
            log("info", f"  [{name}] Ballotpedia image confirmed → {store_url[:80]}")
            return
        log("info", f"  [{name}] Ballotpedia URL not accessible — trying Wikipedia")
    else:
        log("info", f"  [{name}] Ballotpedia API found no image — trying Wikipedia")

    # Fast path 2: query Wikipedia API directly (no LLM call needed)
    # Note: tried after Ballotpedia to avoid name-collision false positives
    # (e.g. "Jeff Wadlin" matching "Jeff Wadlow" the film director).
    log("info", f"  [{name}] Trying Wikipedia API lookup...")
    wiki_url = await _lookup_wikipedia_image(name, context=search_context)
    if wiki_url:
        log("info", f"  [{name}] Wikipedia API returned: {wiki_url[:80]}")
        best_url = await _best_accessible_image_url(wiki_url)
        if best_url:
            candidate["image_url"] = best_url
            log("info", f"  [{name}] Wikipedia image confirmed -> {best_url[:80]}")
            return
        accessible, final_url = await _check_url_accessible(wiki_url)
        if accessible:
            store_url = final_url if _is_valid_image_url(final_url) else wiki_url
            candidate["image_url"] = store_url
            log("info", f"  [{name}] Wikipedia image confirmed → {store_url[:80]}")
            return
        log("info", f"  [{name}] Wikipedia URL not accessible — falling back to agent search")
    else:
        log("info", f"  [{name}] Wikipedia API found no image — falling back to agent search")

    # Fast path 3: inspect candidate website/profile pages for image metadata.
    log("info", f"  [{name}] Inspecting known candidate pages for image metadata...")
    page_url = await _lookup_known_page_image(candidate)
    if page_url:
        candidate["image_url"] = page_url
        log("info", f"  [{name}] Candidate page image confirmed -> {page_url[:80]}")
        return
    log("info", f"  [{name}] Known pages yielded no usable image - trying Serper Image Search")

    # Fast path 4: query Serper Images API directly
    log("info", f"  [{name}] Trying Serper Images API lookup...")
    serper_img = await _lookup_serper_image(name, context=search_context, run_budget=run_budget)
    if serper_img:
        candidate["image_url"] = serper_img
        log("info", f"  [{name}] Serper image confirmed -> {serper_img[:80]}")
        return
    log("info", f"  [{name}] Serper Images found no accessible photo - falling back to agent search")

    if low_resolution_fallback:
        candidate["image_url"] = low_resolution_fallback
        log("info", f"  [{name}] Keeping low-resolution fallback -> {low_resolution_fallback[:80]}")
        return

    # Ask the agent to find a working image URL
    from .prompts import IMAGE_SEARCH_SYSTEM, IMAGE_SEARCH_USER

    log("info", f"  [{name}] Running agent image search...")
    try:
        result = await agent_loop_fn(
            IMAGE_SEARCH_SYSTEM,
            IMAGE_SEARCH_USER.format(candidate_name=name),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max_iterations,
            phase_name=f"image-{name[:20]}",
            max_tokens=2048,
            run_budget=run_budget,
        )
        found_url = result.get("image_url")
        if not found_url:
            log("info", f"  [{name}] Agent returned null — no image found")
            return

        log("info", f"  [{name}] Agent returned: {found_url[:80]}")

        # Agent returned a Commons page URL — resolve it
        if "commons.wikimedia.org/wiki/File:" in found_url:
            log("info", f"  [{name}] Agent URL is Commons page — resolving via Special:FilePath")
            direct = await _resolve_wikimedia_commons(found_url)
            if direct:
                candidate["image_url"] = direct
                log("info", f"  [{name}] Commons resolved → {direct[:80]}")
                return
            log("info", f"  [{name}] Agent Commons URL resolution failed — no image stored")
            return

        # Validate and check accessibility
        if _is_valid_image_url(found_url):
            accessible, final_url = await _check_url_accessible(found_url)
            if accessible:
                store_url = final_url if _is_valid_image_url(final_url) else found_url
                candidate["image_url"] = store_url
                log("info", f"  [{name}] Agent image confirmed → {store_url[:80]}")
                return
            log("info", f"  [{name}] Agent URL is not accessible — no image stored")
        else:
            log("info", f"  [{name}] Agent URL failed validation (not a direct image file) — no image stored")

    except RunBudgetExceeded:
        raise
    except Exception as exc:
        log("warning", f"  [{name}] Image resolution error: {exc}")


async def resolve_candidate_images(
    race_json: Dict[str, Any],
    *,
    agent_loop_fn: Callable,
    model: str,
    on_log: Optional[Callable] = None,
    race_id: Optional[str] = None,
    max_iterations: int = 10,
    on_progress: Optional[Callable[[int, str], None]] = None,
    run_budget: RunBudget | None = None,
) -> None:
    """Validate and resolve image URLs for all candidates, running in parallel.

    *on_progress* is an optional ``(pct: int, candidate_name: str) -> None`` callback
    invoked after each candidate's image is resolved, with cumulative completion
    percentage (0-100) and the candidate name.
    """
    candidates = [c for c in race_json.get("candidates", []) if isinstance(c, dict)]
    if not candidates:
        return
    office = race_json.get("office", "")
    jurisdiction = race_json.get("jurisdiction", "")
    total = len(candidates)
    done = 0

    async def _resolve_with_progress(c: Dict[str, Any]) -> None:
        nonlocal done
        resolve_call = _resolve_single_image(
            c,
            agent_loop_fn=agent_loop_fn,
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max_iterations,
            office=office,
            jurisdiction=jurisdiction,
            run_budget=run_budget,
        )
        if run_budget:
            timeout = run_budget.bounded_timeout(60.0, minimum_seconds=5.0, operation="candidate image resolution")
            await asyncio.wait_for(resolve_call, timeout=timeout)
        else:
            await resolve_call
        done += 1
        if on_progress:
            try:
                on_progress(int(done / total * 100), c.get("name", ""))
            except Exception as e:
                logger.debug("Image progress callback failed: %s", e)

    await asyncio.gather(*[_resolve_with_progress(c) for c in candidates])
