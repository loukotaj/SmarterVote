import pytest

from pipeline_client.agent.images import (
    _candidate_page_urls,
    _extract_page_image_urls,
    _resolve_single_image,
    _wikimedia_original_image_url,
)


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
