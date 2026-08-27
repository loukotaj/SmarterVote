import pytest

from pipeline_client.agent.images import (
    _candidate_page_urls,
    _extract_page_image_urls,
    _filename_person_tokens,
    _host_names_another_state,
    _is_mismatched_person_filename,
    _is_rejected_candidate_image,
    _is_untrusted_wikimedia_match,
    _is_valid_image_url,
    _looks_like_archival_photo,
    _looks_like_generic_cms_filename,
    _looks_like_govtrack_reference_headshot,
    _looks_like_non_photo,
    _looks_like_social_profile_avatar,
    _lookup_ballotpedia_image,
    _lookup_wikipedia_image,
    _name_tokens,
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


def test_obituary_repository_image_is_rejected_even_when_it_is_a_direct_photo():
    assert _looks_like_non_photo("https://d1q40j6jx1d8h6.cloudfront.net/Obituaries/46739509/Image_1.jpg")
    assert _looks_like_non_photo("https://example.com/funeral-home/portraits/alex-smith.webp")
    assert not _looks_like_non_photo("https://candidate.example/photos/alex-smith-headshot.jpg")


def test_ballotpedia_submit_photo_placeholder_is_rejected():
    assert _looks_like_non_photo("https://ballotpedia.s3.us-east-1.amazonaws.com/images/thumb/6/68/SubmitPhoto-150px.png")


@pytest.mark.asyncio
async def test_ballotpedia_lookup_drops_submit_photo_placeholder(monkeypatch):
    async def fake_lookup(candidate_name: str):
        return "https://ballotpedia.s3.us-east-1.amazonaws.com/images/thumb/6/68/SubmitPhoto-150px.png"

    monkeypatch.setattr("pipeline_client.agent.images._ballotpedia_lookup", fake_lookup)

    assert await _lookup_ballotpedia_image("Salomon Hernandez") is None


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
async def test_resolve_single_image_replaces_govtrack_reference_headshot(monkeypatch):
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


def test_looks_like_govtrack_reference_headshot_is_specific_to_govtrack_pattern():
    assert _looks_like_govtrack_reference_headshot("https://www.govtrack.us/static/legislator-photos/412609-200px.jpeg")
    assert not _looks_like_govtrack_reference_headshot("https://example.com/static/legislator-photos/412609-200px.jpeg")
    assert not _looks_like_govtrack_reference_headshot("https://www.govtrack.us/congress/members/french_hill/412609")


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


def test_site_theme_template_asset_is_rejected_as_non_photo():
    """A stock banner shipped with the website template is not a headshot."""
    assert _looks_like_non_photo("https://www.votevarian2026.com/templates/political20_header.png")
    assert _looks_like_non_photo("https://example.org/themes/campaign/masthead.jpg")
    assert not _looks_like_non_photo("https://www.votevarian2026.com/images/keith-varian.jpg")


def test_social_profile_avatar_detected_only_for_profile_images():
    assert _looks_like_social_profile_avatar("https://pbs.twimg.com/profile_images/1328143625339940864/abcDEfg_400x400.jpg")
    assert not _looks_like_social_profile_avatar("https://pbs.twimg.com/media/GpQrStU.jpg")
    assert not _looks_like_social_profile_avatar("https://candidate.example/photos/alex-smith.jpg")


def test_brightspot_image_cdn_url_without_extension_is_a_valid_image():
    """Scripps newsroom photos are served from a transforming CDN path."""
    url = (
        "https://ewscripps.brightspotcdn.com/dims4/default/9cf5bc0/2147483647/strip/true/"
        "crop/1147x639+0+0/resize/1147x639!/quality/90/"
        "?url=http%3A%2F%2Fewscripps-brightspot.s3.amazonaws.com%2Fee%2F5d%2Fabc%2Fshot.png"
    )
    assert _is_valid_image_url(url)


def test_candidate_questionnaire_page_maps_each_photo_to_its_own_candidate():
    """A multi-candidate voter guide must not give everyone the article hero."""
    html = """
    <meta property="og:image" content="/hero-article-card.jpg">
    <h2>Salomon Hernandez Sr.</h2>
    <img src="/photos/shot-a.png" width="1147" height="639" alt="">
    <p>Salomon Hernandez Sr. has lived and worked in Tampa for decades.</p>
    <h2>Keith Varian</h2>
    <img src="/photos/shot-b.png" width="1147" height="644" alt="">
    <p>Keith Varian is a small business owner.</p>
    """

    hernandez = _extract_page_image_urls(html, "https://news.example/guide", "Salomon Hernandez")
    varian = _extract_page_image_urls(html, "https://news.example/guide", "Keith Varian")

    assert hernandez[0] == "https://news.example/photos/shot-a.png"
    assert varian[0] == "https://news.example/photos/shot-b.png"


def test_candidate_page_urls_include_cited_candidate_questionnaire():
    """The questionnaire is often the only published photo of an NPA candidate."""
    candidate = {
        "name": "Keith Varian",
        "website": None,
        "links": [{"url": "https://ballotpedia.org/Keith_Varian", "type": "ballotpedia"}],
        "summary_sources": [
            {
                "url": "https://www.tampabay28.com/news/election-2026/meet-the-candidates-questionnaire-for-us-district-14",
                "type": "news",
                "title": "Meet the candidates: Questionnaire for US District 14",
            },
            {"url": "https://floridapolitics.com/archives/814008-general-coverage/", "type": "news"},
        ],
    }

    pages = _candidate_page_urls(candidate)

    assert pages == ["https://www.tampabay28.com/news/election-2026/meet-the-candidates-questionnaire-for-us-district-14"]


def test_wordpress_theme_directory_headshot_is_not_mistaken_for_site_furniture():
    """Campaign sites routinely serve the real portrait from wp-content/themes/."""
    assert not _looks_like_non_photo("https://beltranforcongress.com/wp-content/themes/beltran/headshot-color.jpg")
    assert not _looks_like_non_photo("https://example.org/wp-content/themes/campaign/img/jane-doe.jpg")
    # Only a theme asset that also reads as furniture is rejected.
    assert _looks_like_non_photo("https://example.org/wp-content/themes/campaign/img/masthead.jpg")


def test_cited_questionnaire_outranks_bare_campaign_homepage():
    """A homepage's first image is often a slogan graphic; the questionnaire is a portrait."""
    candidate = {
        "name": "Keith Varian",
        "website": "https://www.votevarian2026.com/",
        "summary_sources": [
            {
                "url": "https://news.example/news/election-2026/meet-the-candidates-district-14",
                "title": "Meet the candidates: Questionnaire for US District 14",
            }
        ],
    }

    assert _candidate_page_urls(candidate) == [
        "https://news.example/news/election-2026/meet-the-candidates-district-14",
        "https://www.votevarian2026.com/",
    ]


def test_campaign_policy_graphic_is_rejected_as_non_photo():
    """Policy one-pagers live beside real photos in a site's media directory."""
    assert _looks_like_non_photo("https://www.votevarian2026.com/UserFiles/image/Copy_of_Plan_fore_the_Future_(3).jpg")
    assert _looks_like_non_photo("https://example.org/uploads/my-agenda.png")
    assert _looks_like_non_photo("https://example.org/uploads/yard-sign.png")
    assert not _looks_like_non_photo("https://example.org/UserFiles/image/keith-varian-portrait.jpg")


def test_bare_official_homepage_does_not_outrank_candidate_questionnaire():
    """The official bonus is for profile pages, not a bare domain root."""
    candidate = {
        "name": "Keith Varian",
        "links": [{"url": "https://www.votevarian2026.com/", "type": "official"}],
        "summary_sources": [
            {
                "url": "https://news.example/news/election-2026/meet-the-candidates-district-14",
                "title": "Meet the candidates: Questionnaire for US District 14",
            }
        ],
    }

    assert _candidate_page_urls(candidate) == [
        "https://news.example/news/election-2026/meet-the-candidates-district-14",
        "https://www.votevarian2026.com/",
    ]


def test_generic_cms_filename_is_rejected_as_non_photo():
    """A CMS auto-name carries no identity; on a news site it is article art."""
    # fl-house-06-2026 stored this for Michael Gist: an Ohio Capital Journal
    # article graphic showing two other men, not a headshot.
    assert _looks_like_non_photo("https://ohiocapitaljournal.com/wp-content/uploads/2024/06/download-83.png")
    assert _looks_like_non_photo("https://example.org/uploads/unnamed.jpg")
    assert _looks_like_non_photo("https://example.org/uploads/img_1024.jpeg")
    assert _looks_like_non_photo("https://example.org/uploads/photo.png")


def test_generic_cms_filename_check_keeps_named_and_dated_photos():
    """Named portraits and dated capture names must still pass."""
    # The newsroom questionnaire portraits relied on by fl-house-14-2026.
    assert not _looks_like_generic_cms_filename(
        "https://ewscripps-brightspot.s3.amazonaws.com/ee/5d/abc/screenshot-2026-07-30-154741.png"
    )
    assert not _looks_like_generic_cms_filename(
        "https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/Andrew_Parrott_20241210_123816.jpeg"
    )
    # A "/downloads/" directory is not a generic *filename*.
    assert not _looks_like_generic_cms_filename("https://example.org/downloads/jane-doe.jpg")


_BP = "https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/"


def test_ballotpedia_file_named_for_another_person_is_rejected():
    """Ballotpedia's own markup mislabels photos, so the filename must match.

    On https://ballotpedia.org/Dan_Osborn the Nebraska Senate votebox served
    ``Audrey_Hatch_20240808_095600.jpg`` under ``alt="Image of Dan Osborn"``.
    Both the page and the alt text vouched for it, so only the filename
    revealed that ne-senate-2026 had stored a stranger's face.
    """
    assert _is_mismatched_person_filename(_BP + "Audrey_Hatch_20240808_095600.jpg", "Dan Osborn")
    assert _is_mismatched_person_filename(_BP + "Mike_Marvin_2026-04-29_180732.png", "Dan Osborn")
    # An opponent's portrait must not migrate across a race's roster either.
    assert _is_mismatched_person_filename(_BP + "Randy_Weber.jpg", "Thurman Bill Bartie")
    # co-house-04-2026 stored John Padora Jr's thumbnail for Douglas Mangeris,
    # picked off a votebox listing every other candidate in the race.
    assert _is_mismatched_person_filename(_BP + "JohnPadoraJr2025.jpg", "Douglas Mangeris")
    # A file naming an entirely different person is caught even when the
    # candidate's own name appears nowhere in it.
    assert _is_mismatched_person_filename(_BP + "Jason_Poulos_2026.jpg", "Matthew Cook")


def test_ballotpedia_filename_check_trusts_a_file_naming_this_candidate():
    """Descriptive self-uploads must survive; the page vouches for them.

    Auditing all 506 published races showed these outnumber real mismatches,
    so a shared name token is treated as confirmation rather than noise. The
    cost is a shared *given* name (an Ameriprise adviser "wayne-verity" stored
    for Wayne Thornton); that case is caught by _NON_HEADSHOT_HOSTS instead.
    """
    assert not _is_mismatched_person_filename(_BP + "Connie-Centered_20260428.png", "Connie Chan")
    assert not _is_mismatched_person_filename(_BP + "IlhanPortrait3-scaled-1.jpeg", "Ilhan Omar")
    assert not _is_mismatched_person_filename(_BP + "meet-paige_20260701.jpg", "Paige Cognetti")
    # Whole-token match, so a short given name cannot be satisfied by a
    # substring: "Dan" must not be found inside "Jordan".
    assert _is_mismatched_person_filename(_BP + "Jordan_Smith_2026.jpg", "Dan Osborn")


def test_mc_and_de_surnames_are_not_condemned_by_camelcase_splitting():
    """A camelCase split fractures "McGuire"; the flattened name must match.

    Before this, the audit flagged 27 correct photos -- essentially every
    Mc-, Mac-, De- and La- surname in the catalog.
    """
    assert not _is_mismatched_person_filename(_BP + "Mike_McGuire.jpg", "Mike McGuire")
    assert not _is_mismatched_person_filename(_BP + "Mark-DeSaulnier.jpg", "Mark DeSaulnier")
    assert not _is_mismatched_person_filename(_BP + "Betty_McCollum.jpg", "Betty McCollum")
    assert not _is_mismatched_person_filename(_BP + "NickLaLota24.jpg", "Nicholas J. LaLota")


def test_ballotpedia_misspellings_are_tolerated():
    """Ballotpedia typos still depict the right person, so allow a near miss."""
    assert not _is_mismatched_person_filename(_BP + "Tom_Periello.jpg", "Tom Perriello")
    assert not _is_mismatched_person_filename(_BP + "Jessi_Eben.jpg", "Jessi Ebben")
    assert not _is_mismatched_person_filename(_BP + "Christina-Bohannon.jpg", "Christina Bohannan")
    # Far apart is still a different person, not a typo.
    assert _is_mismatched_person_filename(_BP + "Audrey_Hatch_2024.jpg", "Dan Osborn")


def test_ballotpedia_filename_check_tolerates_generational_suffixes():
    """ "Clyde W. Jones, Jr." must resolve to "jones", not to the suffix."""
    assert not _is_mismatched_person_filename(_BP + "Clyde_Jones_2026.jpg", "Clyde W. Jones, Jr.")
    assert not _is_mismatched_person_filename(_BP + "Jeffrey_Hulum_III.jpg", "Jeffrey Hulum III")


def test_ballotpedia_filename_check_keeps_the_candidates_own_photo():
    """Matching either the given name or the surname is enough."""
    assert not _is_mismatched_person_filename(_BP + "William_Timmons.jpg", "William Timmons")
    assert not _is_mismatched_person_filename(_BP + "Jessica-Ethridge.PNG", "Jessica Ethridge")
    # camelCase run: "PeteRicketts2015" -> pete / ricketts
    assert not _is_mismatched_person_filename(_BP + "PeteRicketts2015.jpg", "Pete Ricketts")
    assert not _is_mismatched_person_filename(_BP + "ThurmanBartie2026.jpg", "Thurman Bill Bartie")
    # A married/maiden double surname still matches on the shared token.
    assert not _is_mismatched_person_filename(_BP + "Chauna_Banks-Daniel.jpg", "Chauna Banks")


def test_ballotpedia_filename_check_ignores_files_that_name_nobody():
    """Candidate-submitted uploads carry no name and must not be discarded.

    Requiring two name-like tokens is what protects these: one bare token is
    too weak a signal to overrule the page the image was found on.
    """
    assert not _is_mismatched_person_filename(_BP + "IMG-20260117-WA0002_20260813_173322_32663_1.jpg", "Lewis Mizrahi")
    assert not _is_mismatched_person_filename(_BP + "Carl4congress_profile.jpg", "Carl Boyanton")
    assert not _is_mismatched_person_filename(_BP + "Monique-Ballotpedia.jpg", "Monique Appeaning")
    assert not _is_mismatched_person_filename(_BP + "LRG-Headshot_202604.jpg", "Lindsay Garcia")
    # Non-Ballotpedia hosts are out of scope: on an arbitrary campaign host a
    # filename is as likely to be a slogan as a name, and "GrahamforMaine"
    # legitimately omits Graham Platner's surname.
    assert not _is_mismatched_person_filename("https://example.org/uploads/Audrey_Hatch.jpg", "Dan Osborn")


def test_images_inside_a_rotating_widget_are_ignored():
    """A carousel cycles through other people, so its slides aren't portraits."""
    html = (
        "<html><body>"
        '<div class="question_carousel"><div class="item active">'
        '<img src="/files/other_person.jpg" alt="Dan Osborn" width="200" height="300"/>'
        "</div></div>"
        '<div class="infobox"><img src="/files/real-portrait.jpg" alt="Dan Osborn"/></div>'
        "</body></html>"
    )
    urls = _extract_page_image_urls(html, "https://example.org/Dan_Osborn", "Dan Osborn")
    assert not any("other_person" in u for u in urls)
    assert any("real-portrait" in u for u in urls)


def test_accented_surnames_survive_tokenization():
    """A diacritic must not delete the surname from every name comparison.

    "Pena" with a tilde tokenized as "pe" + "a", both under the length floor,
    so only the given name survived -- and tx-house-37-2026 stored a 1945 press
    photo of the actress Lauren Bacall for Lauren B. Pena, matched on "Lauren"
    alone. This weakened every guard for any candidate with a non-ASCII name.
    """
    assert _name_tokens("Lauren B. Peña") == {"lauren", "pena"}
    assert _name_tokens("José García") == {"jose", "garcia"}

    bacall = (
        "https://upload.wikimedia.org/wikipedia/commons/7/76/" "Lauren_Bacall_1945_press_photo.jpg?utm_source=en.wikipedia.org"
    )
    assert _is_untrusted_wikimedia_match(bacall, "Lauren B. Peña")


def test_filename_tokens_ignore_the_query_string():
    """Tracking parameters are not part of the name the file carries."""
    url = _BP + "Jane_Doe.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail"
    assert _filename_person_tokens(url) == ["jane", "doe"]


def test_pre_1980_year_in_filename_marks_an_archival_photo():
    """A historical namesake is a recurring failure mode."""
    assert _looks_like_archival_photo("https://x/Lauren_Bacall_1945_press_photo.jpg")
    assert _looks_like_archival_photo("https://x/Henry_Ward_Beecher_1863.jpg")
    # Current-cycle dates and capture stamps must not trip it.
    assert not _looks_like_archival_photo("https://x/Jane_Doe_2026.jpg")
    assert not _looks_like_archival_photo("https://x/Rick_Edmonds_202403.jpg")
    assert not _looks_like_archival_photo("https://x/IMG-20260117-WA0002.jpg")


def test_conflicting_middle_initial_marks_a_namesake():
    """Only a middle initial separated a candidate from a dead executive.

    va-house-04-2026 stored the Wikipedia portrait of Robert E. Murray, the
    Murray Energy chief executive who died in 2020, for candidate Robert P.
    Murray. Given and family names both matched.
    """
    assert _is_mismatched_person_filename(
        "https://upload.wikimedia.org/wikipedia/commons/5/53/Robert_E._Murray_%28crop%29.jpg",
        "Robert P. Murray",
    )
    # The candidate's own photo, and a file carrying no initial, both stand.
    assert not _is_mismatched_person_filename(_BP + "Robert_P._Murray.jpg", "Robert P. Murray")
    assert not _is_mismatched_person_filename(_BP + "Robert_Murray_2026.jpg", "Robert P. Murray")
    assert not _is_mismatched_person_filename(_BP + "Frank_D._Lucas.jpg", "Frank D. Lucas")


def test_middle_initial_must_stand_alone_as_a_word():
    """A longer form of the given name is not a middle initial.

    Flattening the filename reads the "n" of "StevenParsons" as an initial and
    rejects Steve G. Parsons' own photo.
    """
    assert not _is_mismatched_person_filename(_BP + "StevenParsons24.jpeg", "Steve G. Parsons")
    # A campaign slogan on an arbitrary host must not trip it either.
    assert not _is_mismatched_person_filename(
        "https://images.squarespace-cdn.com/x/GrahamforMaine_HeroPhoto.jpg", "Graham Platner"
    )


def test_licensed_stock_photo_hosts_are_rejected():
    """A stock library comp is never a candidate portrait, and republishing
    one is a licensing problem on top of a factual one.

    Twice this session a Getty archive photo was stored as a headshot: a 1947
    picture of jazz singer Mildred Bailey for a candidate named Mildred Hall
    (matched via "Carnegie HALL"), and a 1989 picture of British astronaut
    candidates Helen Sharman and Timothy Mace for Tim S. Sharman. The rule had
    lived only in the research prompt, so it kept recurring.
    """
    assert _looks_like_non_photo(
        "https://media.gettyimages.com/id/2158763188/photo/"
        "helen-sharman-and-timothy-mace-candidates-hoping-to-join.jpg?s=612x612"
    )
    assert _looks_like_non_photo("https://www.shutterstock.com/image-photo/senator-portrait-123.jpg")
    assert _looks_like_non_photo("https://www.alamy.com/stock-photo/x.jpg")
    # A real portrait on a normal host is untouched.
    assert not _looks_like_non_photo("https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/Joe_Wilson.jpeg")


def test_campaign_button_is_not_a_headshot():
    """ny-house-18-2026 stored a campaign button graphic for Jackie Auringer."""
    assert _looks_like_non_photo("https://winwithjackie.com/campaign-button.png")
    assert _looks_like_non_photo("https://example.org/sticker-2026.png")
    assert not _looks_like_non_photo("https://winwithjackie.com/jackie-headshot.jpg")


def test_non_photo_tokens_do_not_condemn_names_containing_them():
    """A substring test reads "icon" inside "NikiConforti".

    Auditing the published catalog caught this rejecting real portraits, so
    a token only counts when it is not a fragment of a longer word.
    """
    assert not _looks_like_non_photo("https://example.org/NikiConforti2.png")
    assert not _looks_like_non_photo("https://example.org/Bannerman_Jane.jpg")
    assert not _looks_like_non_photo("https://example.org/Seale_John.jpg")
    assert not _looks_like_non_photo("https://example.org/Logothetis_Maria.jpg")
    # Real hits still land, including a trailing plural.
    assert _looks_like_non_photo("https://example.org/site-icon.png")
    assert _looks_like_non_photo("https://example.org/shoffner-creamlogos3.png")
    assert _looks_like_non_photo("https://static1.squarespace.com/x/halliewebsiteshoffnerhomepage.png")


def test_responsive_width_suffix_is_not_an_archival_year():
    """ "-1920w" is an image width. Reading it as a year rejected real photos.

    Squarespace and Webflow append these to nearly every image, so the first
    version of the archival check condemned portraits wholesale -- including a
    file named "Sheri+Biggs+Headshot-1920w.png".
    """
    assert not _looks_like_archival_photo("https://example.org/Sheri+Biggs+Headshot-1920w.png")
    assert not _looks_like_archival_photo("https://example.org/McDowell+Card+1920x1000.jpg")
    assert not _looks_like_non_photo("https://example.org/Kingston-+Jim_Color-1920w.jpg")
    # A genuine archive year still reads as one.
    assert _looks_like_archival_photo("https://example.org/Cliff_Johnson_-_Houston_Astros_-_1976.jpg")


def test_group_and_share_card_images_are_rejected():
    """A family portrait is not a headshot, whatever the separator."""
    assert _looks_like_non_photo("https://example.org/Scott_Family-web-1920w.jpg")
    assert _looks_like_non_photo("https://example.org/tom-sell-family.jpg")
    assert _looks_like_non_photo("https://example.org/McDowell+Social+Share+Card+1+-+1920x1000.jpg")
    assert _looks_like_non_photo("https://example.org/fb_share.png")
    # A surname that merely starts the same way is untouched.
    assert not _looks_like_non_photo("https://example.org/Familia_Jose.jpg")


def test_image_hosted_by_another_states_outlet_is_rejected():
    """A state's news outlet covers that state's politicians.

    tn-house-07-2026 stored media.newjerseyglobe.com's 2021 photo of a Mercer
    County, New Jersey commissioner named Andrew Koontz as the headshot for the
    Tennessee independent of the same name. The filename ("KBS_3310") named
    nobody, so only the host revealed it.
    """
    assert _host_names_another_state("https://media.newjerseyglobe.com/x/KBS_3310-464x290.jpg", "tn-house-07-2026")
    # The state's own outlet is fine.
    assert not _host_names_another_state("https://www.texastribune.org/x/a.jpg", "tx-house-12-2026")


def test_state_host_check_disambiguates_virginia_from_west_virginia():
    """ "westvirginia" must not be read as "virginia", or vice versa."""
    assert not _host_names_another_state("https://westvirginiawatch.com/x/a.jpg", "wv-house-02-2026")
    assert _host_names_another_state("https://westvirginiawatch.com/x/a.jpg", "va-house-04-2026")
    assert _host_names_another_state("https://virginiamercury.com/x/a.jpg", "wv-house-02-2026")


def test_state_host_check_ignores_hosts_that_name_no_state():
    """Two-letter codes collide with ordinary words, so only full names count.

    "lailluminator.com" is Louisiana's outlet but contains no full state name,
    and matching the code "la" would also hit unrelated hosts.
    """
    assert not _host_names_another_state("https://lailluminator.com/x/Larry-Davis-2.jpg", "la-house-06-2026")
    assert not _host_names_another_state("https://lailluminator.com/x/a.jpg", "tn-house-07-2026")
    assert not _host_names_another_state("https://s3.amazonaws.com/ballotpedia-api4/x/a.jpg", "sc-house-02-2026")
    assert not _host_names_another_state("https://upload.wikimedia.org/x/a.jpg", "ny-house-08-2026")
    # No race id means no judgement.
    assert not _host_names_another_state("https://media.newjerseyglobe.com/x/a.jpg", None)


def test_state_host_check_ignores_a_cdn_region_subdomain():
    """A CDN encodes its data centre in a subdomain, not its coverage area.

    "bloximages.newyork1.vip.townnews.com" is TownNews infrastructure serving a
    Florida paper; reading "newyork" from it rejected a correct photo. Only the
    registrable domain is considered.
    """
    assert not _host_names_another_state("https://bloximages.newyork1.vip.townnews.com/x/a.jpg", "fl-house-24-2026")


def test_retail_product_images_are_rejected():
    """A surname that is also a common noun drags in shopping results.

    mi-house-13-2026 stored a Home Depot pendant light fixture as the headshot
    for a candidate named Raelyn Light. The surname genuinely appears in
    "pendant-lights", so the filename guard could not catch it -- only the host
    and the /productImages/ path do.
    """
    assert _looks_like_non_photo(
        "https://images.thdstatic.com/productImages/2a4b/svn/" "matte-black-rennnsan-pendant-lights-pl8101-73228-64_1000.jpg"
    )
    assert _looks_like_non_photo("https://m.media-amazon.com/images/I/71abc.jpg")
    assert _looks_like_non_photo("https://example.org/productImages/x.jpg")
    # Ordinary candidate portraits are untouched.
    assert not _looks_like_non_photo("https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/MarkTeixeira2026.png")


def test_crowdfunding_platform_images_are_rejected():
    """A fundraising banner is collateral, not a portrait.

    mi-house-10-2026 stored a GoFundMe graphic advertising a candidate's book --
    headline text, bullet points, a donate button and a QR code, with his face
    in one corner -- as his headshot. The filename was a hash, so only the host
    identifies it.
    """
    assert _looks_like_non_photo("https://images.gofundme.com/HiJ6EOPm6pF39agEz0M8I9plzx8=/1200x900/x.jpg")
    assert _looks_like_non_photo("https://www.kickstarter.com/assets/x.png")
    assert not _looks_like_non_photo("https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/Joe_Wilson.jpeg")


def test_memorial_and_obituary_hosts_are_rejected():
    """An obituary portrait is of someone who has died, not a candidate.

    ca-house-10-2026 stored "jackava.b-cdn.net/deceased/d_1758200993193.webp"
    for Jeffrey Frese. The marker list already covered /obituaries/ and
    funeral homes but not /deceased/, which is the path memorial CDNs
    actually use.
    """
    assert _looks_like_non_photo("https://jackava.b-cdn.net/deceased/d_1758200993193.webp")
    assert _looks_like_non_photo("https://example.org/in-memoriam/portrait.jpg")
    assert _looks_like_non_photo("https://www.legacy.com/obituaries/name/x-obituary")
    assert _looks_like_non_photo("https://tributearchive.com/x/y.jpg")
    # An ordinary candidate portrait is untouched.
    assert not _looks_like_non_photo("https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/Joe_Wilson.jpeg")


@pytest.mark.parametrize(
    "url",
    [
        "https://ssl.gstatic.com/atari/images/sociallinks/linkedin_white_28dp.png",
        "https://example.com/assets/icons/twitter.png",
        "https://example.com/img/facebook_24dp.png",
    ],
)
def test_ui_icon_assets_are_rejected(url):
    assert _looks_like_non_photo(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://www.wittaforcongress.com/images/og-image.jpg",
        "https://hannonforcongress.com/social-card.png",
        "https://example.com/assets/og_image.png",
        "https://example.com/assets/twitter-card.jpg",
    ],
)
def test_social_cards_are_rejected(url):
    assert _looks_like_non_photo(url) is True


@pytest.mark.parametrize(
    "url,rejected",
    [
        # A page-wide hero strip: CA-44 stored one as Nanette Barragan's portrait.
        ("https://barragan.house.gov/wp-content/uploads/2023/07/WebsiteUpdate2-1920x860.jpg", True),
        ("https://example.com/img/candidate-2000x600.jpg", True),
        # Portrait and square crops must survive.
        ("https://example.com/img/candidate-800x1000.jpg", False),
        ("https://votevets.org/wp-content/uploads/2025/12/Shawn-2026-headshot-Updated-1200x1200.jpg", False),
        ("https://example.com/img/candidate-1024x985.jpg", False),
    ],
)
def test_banner_aspect_ratio_rejected_portraits_kept(url, rejected):
    assert _looks_like_non_photo(url) is rejected


@pytest.mark.parametrize(
    "url",
    [
        "https://upload.wikimedia.org/wikipedia/commons/2/2c/Eric_Jones_%28solo_climber%29.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/5/5b/Ryan_Kelly_%28American_football%29.JPG",
        "https://upload.wikimedia.org/wikipedia/commons/1/13/James_Burke_%28science_historian%29.jpg",
    ],
)
def test_wikimedia_occupational_namesakes_are_rejected(url):
    assert _looks_like_non_photo(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://imgstore.io/images/2026/05/26/platform-situs-toto-1.webp",
        "https://example.com/img/judi-online.jpg",
        "https://example.com/img/slot-gacor.png",
    ],
)
def test_seo_spam_images_are_rejected(url):
    assert _looks_like_non_photo(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://casasforcongress.com/wp-content/uploads/2024/01/cagop-candidate-1024x985.png",
        "https://example.com/img/txgop-endorsed.png",
        "https://example.com/img/endorsed.jpg",
        "https://example.com/img/endorsement-seal.png",
    ],
)
def test_endorsement_badges_are_rejected(url):
    assert _looks_like_non_photo(url) is True


@pytest.mark.parametrize(
    "url",
    [
        # Real surnames and place names must not trip the spam tokens.
        "https://example.com/photos/hiroshi-bandara.jpg",
        "https://example.com/photos/candidate-from-totowa.jpg",
        "https://example.com/photos/judith-alvarez.jpg",
    ],
)
def test_real_names_survive_seo_spam_rule(url):
    assert _looks_like_non_photo(url) is False


@pytest.mark.parametrize(
    "url",
    [
        # Real official portraits are disambiguated by Congress number, a
        # sequence number, a Flickr id, a party-state tag, or a crop note.
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Jimmy_Gomez_official_portrait_%28light_crop%29.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/x/xx/Adam_Gray%2C_official_portrait_%28119th_Congress%29.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/x/xx/Dina_Titus_official_photo_%281%29.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/x/xx/Dan_Cox_Mar2020_%2849617550556%29.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/x/xx/David_Jolly_%283x4%29.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/x/xx/Sen._Marsha_Blackburn_%28R-TN%29_official_headshot.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/x/xx/Mike_Rogers_%28Alabama_politician%29.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/x/xx/Mike_Flood%2C_official_portrait_%28118th_Congress%29_%28cropped%29.jpg",
    ],
)
def test_genuine_official_portraits_survive_namesake_rule(url):
    assert _looks_like_non_photo(url) is False


@pytest.mark.parametrize(
    "url",
    [
        # Card generators name the file after the candidate; the path gives them away.
        "https://linktr.ee/og/image/wingfieldforcongress.jpg",
        "https://themidtermproject.org/api/og/candidate/barnett-shafina.png",
        "https://example.com/social-card/jane-doe.png",
    ],
)
def test_generated_social_cards_are_rejected_by_path(url):
    assert _looks_like_non_photo(url) is True


def test_ordinary_paths_containing_og_are_not_social_cards():
    """ "og" must match a whole path segment, not a fragment of a word."""
    assert _looks_like_non_photo("https://example.com/photos/ogden-mayor-jane-doe.jpg") is False
    assert _looks_like_non_photo("https://example.com/blog/candidate-headshot.jpg") is False


@pytest.mark.parametrize(
    "url",
    [
        # A real surname must survive: no party-organisation prefix, no badge word.
        "https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/Judy_Chu.jpg",
        "https://example.com/img/Andrew_Sneed_2025.jpeg",
        # "Endorsements" as a page/section slug in the path, not the filename.
        "https://example.com/endorsements/maria-gomez-headshot.jpg",
    ],
)
def test_real_headshots_survive_endorsement_badge_rule(url):
    assert _looks_like_non_photo(url) is False


@pytest.mark.parametrize(
    "url",
    [
        # MediaWiki also disambiguates with a hyphenated suffix, which reads as
        # part of the name to every other check.
        "https://upload.wikimedia.org/wikipedia/commons/4/49/Peter_Williams_-_JPS_Norton_cropped.JPG",
        "https://upload.wikimedia.org/wikipedia/commons/2/2a/Cliff_Johnson_-_Houston_Astros.jpg",
    ],
)
def test_hyphenated_namesake_portraits_are_rejected(url):
    assert _looks_like_non_photo(url) is True


@pytest.mark.parametrize(
    "url",
    [
        # A hyphen inside an ordinary official-portrait name must survive.
        "https://upload.wikimedia.org/wikipedia/commons/x/xx/Maad_Abu-Ghazalah.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/x/xx/Sen._Marsha_Blackburn_-_official_portrait.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/x/xx/Jane_Doe_-_119th_Congress.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/x/xx/Jane_Doe_-_North_Carolina.jpg",
        # Non-Wikimedia hosts are out of scope for this rule.
        "https://example.com/photos/john-smith-city-council.jpg",
    ],
)
def test_genuine_portraits_survive_hyphenated_namesake_rule(url):
    assert _looks_like_non_photo(url) is False


@pytest.mark.parametrize(
    "url,name",
    [
        # Photo jargon is not a name.  Ballotpedia keeps whatever the uploader's
        # camera roll or CMS called the file; all three of these are the RIGHT
        # person, verified by eye.
        ("https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/Press-pic-2_20260617_052426.jpg", "Da'Shone Hughey"),
        ("https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/LankfordPost-2_20260629_205343.jpeg", "Jena Nelson"),
        (
            "https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/Screenshot-20260625-122137-Gallery.jpg",
            "Curtis Goodwin",
        ),
    ],
)
def test_photo_jargon_filenames_are_not_read_as_another_person(url, name):
    assert _is_mismatched_person_filename(url, name) is False


@pytest.mark.parametrize(
    "url,name",
    [
        # A filename naming a real, different person must still be caught.
        ("https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/Audrey_Hatch_20240808.jpg", "Dan Osborn"),
        ("https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/Randy_Weber.jpg", "Thurman Bill Bartie"),
    ],
)
def test_real_other_person_filenames_are_still_caught(url, name):
    assert _is_mismatched_person_filename(url, name) is True


def test_a_lone_name_token_beside_jargon_is_not_enough_to_condemn():
    """Stripping jargon can leave one token, and one token proves nothing.

    "Press_Hatch_2026" reduces to just "hatch", which is as consistent with a
    photographer credit or a place as with another candidate, so the rule's
    two-token floor correctly declines to reject.
    """
    url = "https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/Press_Hatch_2026.jpg"
    assert _is_mismatched_person_filename(url, "Dan Osborn") is False


def test_commons_resolved_image_must_match_the_candidate_name():
    wrong_person = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Jane_Doe_portrait.jpg"
    assert _looks_like_non_photo(wrong_person) is False
    assert _is_rejected_candidate_image(wrong_person, "John Smith") is True


@pytest.mark.asyncio
async def test_commons_resolution_does_not_bypass_the_non_photo_guards(monkeypatch):
    """A Commons file page must be judged, not trusted because it resolved.

    NJ-03 re-acquired "Ryan_Kelly_(American_football).JPG" — a Colts lineman —
    the refresh after it had been repaired, because the Commons branch stored
    whatever Special:FilePath returned and returned early.
    """
    from pipeline_client.agent import images as images_module

    namesake = "https://upload.wikimedia.org/wikipedia/commons/5/5b/Ryan_Kelly_%28American_football%29.JPG"

    async def fake_resolve(url):
        return namesake

    monkeypatch.setattr(images_module, "_resolve_wikimedia_commons", fake_resolve)

    searched = {}

    async def fake_search(*args, **kwargs):
        searched["called"] = True
        return None

    monkeypatch.setattr(images_module, "_search_for_candidate_image", fake_search, raising=False)

    candidate = {
        "name": "Ryan Kelly",
        "image_url": "https://commons.wikimedia.org/wiki/File:Ryan_Kelly_(American_football).JPG",
    }

    await images_module._resolve_single_image(
        candidate,
        agent_loop_fn=None,
        model="test-model",
        race_id="nj-house-03-2026",
    )

    assert candidate["image_url"] != namesake
