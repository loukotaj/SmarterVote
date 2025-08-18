# site_walker.py
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from shared.models import Source, SourceType

from ..constants import ALLOW, DENY


def derive_candidate_pages(homepage: Source, html: str, *, max_links: int = 8) -> list[Source]:
    if not homepage or not getattr(homepage, "url", None) or not html:
        return []
    base = homepage.url
    host = urlparse(base).netloc
    soup = BeautifulSoup(html, "html.parser")
    out: list[Source] = []
    seen: set[str] = set()

    def keep(path: str) -> bool:
        p = path.lower()
        if any(p.startswith(d) for d in DENY):
            return False
        if any(tok in p for tok in ALLOW):
            return True
        # simple heuristics for menu items
        return any(x in p for x in ("/issue", "/policy", "/plan", "/news", "/press"))

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("#") or href.startswith("mailto:"):
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
        out.append(Source(url=link, type=SourceType.WEBSITE, title=(a.get_text() or "").strip()))
        if len(out) >= max_links:
            break
    return out
