import pytest

from pipeline_client.agent.images import (
    _candidate_page_urls,
    _extract_page_image_urls,
    _looks_like_non_photo,
    _lookup_wikipedia_image,
    _resolve_single_image,
    _wikimedia_original_image_url,
)


def test_homepage_banner_and_collage_are_rejected_as_non_photos():
    # A campaign homepage banner / collage graphic is not a usable headshot.
    assert _looks_like_non_photo("https://static1.squarespace.com/.../halliewebsiteshoffnerhomepage.png")
    assert _looks_like_non_photo("https://images.squarespace-cdn.com/.../shoffner_collage.jpg")
    # A real named photo is kept.
    assert not _looks_like_non_photo("https://images.squarespace-cdn.com/.../Hallie+%2899%29.jpg")


def test_generic_social_card_rejected_and_data_hosts_skipped():
    # FEC/OpenSecrets etc. serve a generic social card, never a headshot.
    assert _looks_like_non_photo("https://www.fec.gov/static/img/social/fec-data.png")
    cand = {
        "name": "Hallie Shoffner",
        "website": "https://www.hallieshoffner.com/",
        "links": [
            {"url": "https://ballotpedia.org/Hallie_Shoffner", "type": "ballotpedia"},
            {"url": "https://www.fec.gov/data/candidate/S6AR00199/", "type": "finance"},
        ],
    }
    # Data/reference hosts are dropped; only the campaign site remains.
    assert _candidate_page_urls(cand) == ["https://www.hallieshoffner.com/"]


def test_extract_page_images_skips_homepage_banner_for_real_headshot():
    html = """
    <meta property="og:image" content="/halliewebsiteshoffnerhomepage.png">
    <img data-src="/Hallie+%2899%29.jpg" width="1200" height="1500" alt="Hallie Shoffner">
    """
    ranked = _extract_page_image_urls(html, "https://example.com/", "Hallie Shoffner")
    assert ranked and "Hallie" in ranked[0]
    assert not any("homepage" in url for url in ranked)


def test_extract_page_images_prefers_large_named_photo_over_social_banner_and_logo():
    html = """
    <meta property="og:image" content="/campaign-banner.png">
    <img src="/shoffner-creamlogos3.png" width="800" height="300" alt="Hallie Shoffner">
    <img data-image="/photos/Hallie-99.jpg" width="5040" height="3360" alt="Hallie Shoffner">
    """

    assert _extract_page_image_urls(html, "https://example.com/", "Hallie Shoffner") == [
        "https://example.com/photos/Hallie-99.jpg"
    ]


def test_extract_page_images_accepts_candidate_profile_open_graph_portrait():
    html = '<meta property="og:image" content="https://cdn.example.com/2731_Grey_2.jpg">'

    assert _extract_page_image_urls(html, "https://lp.org/candidate/jeff-wadlin/", "Jeff Wadlin") == [
        "https://cdn.example.com/2731_Grey_2.jpg"
    ]


def test_extract_page_images_accepts_official_campaign_hero_photo():
    html = """
    <meta property="og:image" content="https://images.squarespace-cdn.com/content/v1/6892a4b7c6b1853d62f8fbfd/57eaa2f9-56ed-4a9f-a377-c226a4f47883/GrahamforMaine_SocialShare.png?format=1500w&content-type=image%2Fpng">
    <img src="https://images.squarespace-cdn.com/content/v1/6892a4b7c6b1853d62f8fbfd/9a251b85-f48f-4e00-8cab-d1c78c1ee8b6/GrahamforMaine_HeroBG.jpg">
    <meta property="og:image" content="https://images.squarespace-cdn.com/content/v1/6892a4b7c6b1853d62f8fbfd/deb90fec-3247-4488-9820-7f07533fd158/GrahamforMaine_HeroPhoto.jpg">
    """

    assert _extract_page_image_urls(html, "https://www.grahamforsenate.com/", "Graham Platner") == [
        "https://images.squarespace-cdn.com/content/v1/6892a4b7c6b1853d62f8fbfd/deb90fec-3247-4488-9820-7f07533fd158/GrahamforMaine_HeroPhoto.jpg"
    ]


def test_extract_page_images_rejects_generic_official_site_scenic_image():
    html = '<meta property="og:image" content="/images/mountain.png">'

    assert _extract_page_image_urls(html, "https://hill.house.gov/", "French Hill") == []


def test_candidate_page_urls_prioritize_candidate_specific_profile():
    candidate = {
        "name": "Jeff Wadlin",
        "website": "https://www.jeffwadlin.com/",
        "links": [
            {"url": "https://lp.org/candidate/jeff-wadlin/", "type": "official"},
            {"url": "https://example.com/news/election", "type": "news"},
        ],
    }

    assert _candidate_page_urls(candidate) == [
        "https://lp.org/candidate/jeff-wadlin/",
        "https://www.jeffwadlin.com/",
        "https://example.com/news/election",
    ]


def test_wikimedia_original_image_url_converts_thumbnail_to_original():
    thumb = "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0b/Hill_French_119th_Congress.jpg/250px-Hill_French_119th_Congress.jpg"

    assert (
        _wikimedia_original_image_url(thumb)
        == "https://upload.wikimedia.org/wikipedia/commons/0/0b/Hill_French_119th_Congress.jpg"
    )


@pytest.mark.asyncio
async def test_resolve_single_image_upgrades_existing_wikimedia_thumbnail(monkeypatch):
    thumb = "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0b/Hill_French_119th_Congress.jpg/250px-Hill_French_119th_Congress.jpg"
    original = "https://upload.wikimedia.org/wikipedia/commons/0/0b/Hill_French_119th_Congress.jpg"
    candidate = {"name": "French Hill", "image_url": thumb}

    async def fake_check(url: str):
        return url == original, url

    async def fail_agent(*args, **kwargs):
        raise AssertionError("agent search should not run for an accessible existing image")

    monkeypatch.setattr("pipeline_client.agent.images._check_url_accessible", fake_check)

    await _resolve_single_image(candidate, agent_loop_fn=fail_agent, model="test")

    assert candidate["image_url"] == original


@pytest.mark.asyncio
async def test_resolve_single_image_replaces_existing_non_photo_url(monkeypatch):
    non_photo = "https://hill.house.gov/images/mountain.png"
    replacement = "https://upload.wikimedia.org/wikipedia/commons/0/0b/Hill_French_119th_Congress.jpg"
    candidate = {"name": "French Hill", "image_url": non_photo}

    async def fake_check(url: str):
        return url == replacement, url

    async def fail_agent(*args, **kwargs):
        raise AssertionError("agent search should not run when Wikipedia finds an image")

    monkeypatch.setattr("pipeline_client.agent.images._check_url_accessible", fake_check)

    async def fake_ballotpedia(name: str):
        return None

    monkeypatch.setattr("pipeline_client.agent.images._lookup_ballotpedia_image", fake_ballotpedia)

    async def fake_wikipedia(name: str, context: str = ""):
        return replacement

    monkeypatch.setattr("pipeline_client.agent.images._lookup_wikipedia_image", fake_wikipedia)

    await _resolve_single_image(candidate, agent_loop_fn=fail_agent, model="test")

    assert candidate["image_url"] == replacement


@pytest.mark.asyncio
async def test_resolve_single_image_replaces_low_resolution_govtrack_reference_photo(monkeypatch):
    low_res = "https://www.govtrack.us/static/legislator-photos/412609-200px.jpeg"
    replacement = "https://upload.wikimedia.org/wikipedia/commons/0/0b/Hill_French_119th_Congress.jpg"
    candidate = {"name": "French Hill", "image_url": low_res}

    async def fake_check(url: str):
        return url == replacement, url

    async def fail_agent(*args, **kwargs):
        raise AssertionError("agent search should not run when Wikipedia finds an image")

    monkeypatch.setattr("pipeline_client.agent.images._check_url_accessible", fake_check)

    async def fake_ballotpedia(name: str):
        return None

    monkeypatch.setattr("pipeline_client.agent.images._lookup_ballotpedia_image", fake_ballotpedia)

    async def fake_wikipedia(name: str, context: str = ""):
        return replacement

    monkeypatch.setattr("pipeline_client.agent.images._lookup_wikipedia_image", fake_wikipedia)

    await _resolve_single_image(candidate, agent_loop_fn=fail_agent, model="test")

    assert candidate["image_url"] == replacement


@pytest.mark.asyncio
async def test_resolve_single_image_falls_back_to_serper_image(monkeypatch):
    replacement = "https://example.com/serper_headshot.jpg"
    candidate = {"name": "Test Candidate", "image_url": None}

    async def fake_check(url: str):
        return True, url

    async def fail_agent(*args, **kwargs):
        raise AssertionError("agent search loop should not run when Serper fast path succeeds")

    monkeypatch.setattr("pipeline_client.agent.images._check_url_accessible", fake_check)

    async def fake_ballotpedia(name: str):
        return None

    monkeypatch.setattr("pipeline_client.agent.images._lookup_ballotpedia_image", fake_ballotpedia)

    async def fake_wikipedia(name: str, context: str = ""):
        return None

    monkeypatch.setattr("pipeline_client.agent.images._lookup_wikipedia_image", fake_wikipedia)

    async def fake_page_image(candidate: dict):
        return None

    monkeypatch.setattr("pipeline_client.agent.images._lookup_known_page_image", fake_page_image)

    async def fake_serper_image(name: str, context: str = "", run_budget=None):
        return replacement

    monkeypatch.setattr("pipeline_client.agent.images._lookup_serper_image", fake_serper_image)

    await _resolve_single_image(candidate, agent_loop_fn=fail_agent, model="test")

    assert candidate["image_url"] == replacement


class _FakeWikipediaResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeWikipediaClient:
    """Simulates the Wikipedia opensearch + pageimages API calls.

    ``opensearch_titles`` maps a search query to the list of titles that
    opensearch would return. ``thumbnails`` maps a page title to the thumbnail
    URL that the pageimages query would return for it.
    """

    def __init__(self, opensearch_titles, thumbnails):
        self.opensearch_titles = opensearch_titles
        self.thumbnails = thumbnails
        self.calls = []

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None, headers=None, **kwargs):
        params = params or {}
        self.calls.append(params)
        if params.get("action") == "opensearch":
            query = params["search"]
            titles = self.opensearch_titles.get(query, [])
            return _FakeWikipediaResponse([query, titles, [], []])
        if params.get("action") == "query":
            title = params["titles"]
            thumb = self.thumbnails.get(title)
            page = {"pageid": 1, "title": title}
            if thumb:
                page["thumbnail"] = {"source": thumb}
            return _FakeWikipediaResponse({"query": {"pages": {"1": page}}})
        raise AssertionError(f"unexpected Wikipedia API call: {params}")


@pytest.mark.asyncio
async def test_lookup_wikipedia_image_rejects_fuzzy_match_with_wrong_surname(monkeypatch):
    # opensearch is fuzzy — "Sam Mead" (a down-ballot candidate with no Wikipedia
    # page) can return "Sam Mendes" (the film director) as its best guess. The
    # surname "Mead" doesn't appear in "Sam Mendes", so it must be rejected.
    fake_client = _FakeWikipediaClient(
        opensearch_titles={"Sam Mead": ["Sam Mendes"]},
        thumbnails={"Sam Mendes": "https://upload.wikimedia.org/wikipedia/commons/sam_mendes.jpg"},
    )
    monkeypatch.setattr("pipeline_client.agent.images.httpx.AsyncClient", fake_client)

    result = await _lookup_wikipedia_image("Sam Mead")

    assert result is None
    # The mismatched title must never reach the pageimages lookup.
    assert all(call.get("action") != "query" for call in fake_client.calls)


@pytest.mark.asyncio
async def test_lookup_wikipedia_image_accepts_matching_surname(monkeypatch):
    fake_client = _FakeWikipediaClient(
        opensearch_titles={"French Hill": ["French Hill"]},
        thumbnails={"French Hill": "https://upload.wikimedia.org/wikipedia/commons/french_hill.jpg"},
    )
    monkeypatch.setattr("pipeline_client.agent.images.httpx.AsyncClient", fake_client)

    result = await _lookup_wikipedia_image("French Hill")

    assert result == "https://upload.wikimedia.org/wikipedia/commons/french_hill.jpg"


@pytest.mark.asyncio
async def test_lookup_wikipedia_image_rejects_same_surname_unrelated_entity(monkeypatch):
    fake_client = _FakeWikipediaClient(
        opensearch_titles={"David Matthews": ["Dave Matthews Band"]},
        thumbnails={"Dave Matthews Band": "https://upload.wikimedia.org/wikipedia/commons/dave_matthews_band.jpg"},
    )
    monkeypatch.setattr("pipeline_client.agent.images.httpx.AsyncClient", fake_client)

    result = await _lookup_wikipedia_image("David Matthews")

    assert result is None
    assert all(call.get("action") != "query" for call in fake_client.calls)


@pytest.mark.asyncio
async def test_lookup_wikipedia_image_rejects_exact_name_composer_thumbnail(monkeypatch):
    fake_client = _FakeWikipediaClient(
        opensearch_titles={"David Matthews": ["David Matthews"]},
        thumbnails={"David Matthews": "https://upload.wikimedia.org/wikipedia/commons/9/9f/David_Matthews_composer.jpg"},
    )
    monkeypatch.setattr("pipeline_client.agent.images.httpx.AsyncClient", fake_client)

    result = await _lookup_wikipedia_image("David Matthews")

    assert result is None


@pytest.mark.asyncio
async def test_resolve_single_image_discards_stale_mismatched_wikimedia_url(monkeypatch):
    # A prior run can persist a mismatched Wikimedia URL onto image_url (e.g. from
    # the opensearch fuzzy-match bug before it was fixed). The existing-URL fast
    # path must not just re-validate it's *accessible* and keep it forever — it
    # needs to notice the filename doesn't match this candidate and re-search.
    mismatched = "https://upload.wikimedia.org/wikipedia/commons/f/fe/Sam_Mendes_in_2022-2.jpg"
    replacement = "https://upload.wikimedia.org/wikipedia/commons/sam_mead.jpg"
    candidate = {"name": "Sam Mead", "image_url": mismatched}

    async def fail_check(url: str):
        raise AssertionError("should not re-validate a mismatched Wikimedia URL as accessible")

    async def fail_agent(*args, **kwargs):
        raise AssertionError("agent search loop should not run when Wikipedia finds an image")

    monkeypatch.setattr("pipeline_client.agent.images._check_url_accessible", fail_check)

    async def fake_ballotpedia(name: str):
        return None

    monkeypatch.setattr("pipeline_client.agent.images._lookup_ballotpedia_image", fake_ballotpedia)

    async def fake_wikipedia(name: str, context: str = ""):
        return replacement

    monkeypatch.setattr("pipeline_client.agent.images._lookup_wikipedia_image", fake_wikipedia)

    async def fake_best_accessible(url: str):
        return url

    monkeypatch.setattr("pipeline_client.agent.images._best_accessible_image_url", fake_best_accessible)

    await _resolve_single_image(candidate, agent_loop_fn=fail_agent, model="test")

    assert candidate["image_url"] == replacement


def test_is_untrusted_wikimedia_match_ignores_non_wikimedia_urls():
    from pipeline_client.agent.images import _is_untrusted_wikimedia_match

    assert not _is_untrusted_wikimedia_match("https://ballotpedia.org/images/Sam_Mendes.jpg", "Sam Mead")
    assert _is_untrusted_wikimedia_match(
        "https://upload.wikimedia.org/wikipedia/commons/f/fe/Sam_Mendes_in_2022-2.jpg", "Sam Mead"
    )
    assert not _is_untrusted_wikimedia_match(
        "https://upload.wikimedia.org/wikipedia/commons/f/fe/Sam_Mead_2026.jpg", "Sam Mead"
    )
    assert _is_untrusted_wikimedia_match(
        "https://upload.wikimedia.org/wikipedia/commons/d/d0/Dave_Matthews_Band.jpg", "David Matthews"
    )
    assert _is_untrusted_wikimedia_match(
        "https://upload.wikimedia.org/wikipedia/commons/9/9f/David_Matthews_composer.jpg", "David Matthews"
    )
