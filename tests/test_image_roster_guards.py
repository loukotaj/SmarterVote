"""Roster-level and social-card image guards (#322).

Two checks a per-candidate resolver cannot make on its own: whether two
candidates in the same race ended up with the same photo, and whether an
official site's meta-tag image is branding rather than a portrait.
"""

from pipeline_client.agent.images import _drop_shared_candidate_images, _looks_like_non_photo


def _log(level, message):
    pass


def test_shared_photo_stays_with_the_candidate_the_filename_names():
    """mi-house-12-2026 gave the incumbent's portrait to her challenger at a smaller size."""
    tlaib = {"name": "Rashida Tlaib", "image_url": "https://cdn.ballotpedia.org/images/Rashida-Tlaib.PNG"}
    hooper = {"name": "James Hooper", "image_url": "https://cdn.ballotpedia.org/images/thumbs/100/100/Rashida-Tlaib.PNG"}

    assert _drop_shared_candidate_images([tlaib, hooper], _log) == 1
    assert tlaib["image_url"]
    assert hooper["image_url"] is None


def test_shared_photo_naming_nobody_is_cleared_from_everyone():
    a = {"name": "Angie Boone", "image_url": "https://cms.example.com/image.jpg"}
    b = {"name": "Keith Varian", "image_url": "https://cms.example.com/thumb/image.jpg"}

    assert _drop_shared_candidate_images([a, b], _log) == 2
    assert a["image_url"] is None
    assert b["image_url"] is None


def test_distinct_photos_are_left_alone():
    a = {"name": "Pete Ricketts", "image_url": "https://cdn.example.com/Pete-Ricketts.jpg"}
    b = {"name": "Dan Osborn", "image_url": "https://cdn.example.com/Dan-Osborn.jpg"}

    assert _drop_shared_candidate_images([a, b], _log) == 0
    assert a["image_url"] and b["image_url"]


def test_candidates_without_photos_are_not_treated_as_sharing_one():
    a = {"name": "Pete Ricketts", "image_url": None}
    b = {"name": "Dan Osborn"}

    assert _drop_shared_candidate_images([a, b], _log) == 0


def test_official_site_meta_image_is_not_a_headshot():
    """tx-house-13-2026 stored the House seal as Rep. Ronny Jackson's photo."""
    assert _looks_like_non_photo("https://jackson.house.gov/images/facebook-meta.jpg")
    assert _looks_like_non_photo("https://example.org/assets/og-image.png")
    assert _looks_like_non_photo("https://example.org/assets/twitter-image.jpg")
    assert _looks_like_non_photo("https://example.org/assets/social-web.jpg")
    assert not _looks_like_non_photo("https://example.org/assets/JaneDoe.jpg")
