"""The decision rule that turns what a vision model saw into keep-or-discard.

Every case here is an image that was published live on a real race, with the
observations the model actually returned for it.
"""

import asyncio

import httpx
import pytest

from pipeline_client.agent.image_vision import PhotoVerdict, inspect_candidate_photo, verdict_from_observations


def _seen(**overrides):
    """Observations for an ordinary usable portrait, before overrides."""
    base = {
        "faces": 1,
        "is_photograph": True,
        "obscured_face": False,
        "subject_is_child": False,
        "era": "contemporary",
        "uniform_or_costume": None,
        "overlaid_text": False,
        "reason": "clear headshot of a single adult",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "observations,expected_reason",
    [
        # jumpotron.png was a bridge and a water tower; casas was a party rosette.
        (_seen(faces=0, is_photograph=False), "not a photograph"),
        (_seen(faces=0), "no face"),
        # A union rally, a podcast split-screen, an Adelaide Footy League still.
        (_seen(faces=8), "8 people"),
        (_seen(faces=2), "2 people"),
        # A motorcycle racer mid-race; a Colts lineman in a helmet.
        (_seen(obscured_face=True), "obscured"),
        # A child in a youth baseball uniform, stored for a Delaware candidate.
        (_seen(subject_is_child=True), "child"),
        # Mike_Nichols.jpg was a mid-century publicity still.
        (_seen(era="archival"), "archival"),
        (_seen(uniform_or_costume="sports jersey"), "sports jersey"),
    ],
)
def test_unusable_images_are_discarded(observations, expected_reason):
    verdict = verdict_from_observations(observations)
    assert verdict.usable is False
    assert expected_reason in verdict.reason


@pytest.mark.parametrize(
    "observations",
    [
        _seen(),
        # Photographed in front of his own campaign backdrop.
        _seen(overlaid_text=True),
        # A business name printed on the subject's shirt.
        _seen(overlaid_text=True, reason="branding text on the subject's shirt"),
        # Religious dress is not disqualifying; a candidate may be a cleric.
        _seen(uniform_or_costume="religious robes"),
        # A model that omits a field must not cause a rejection.
        {"faces": 1, "is_photograph": True, "reason": "fine"},
    ],
)
def test_usable_images_are_kept(observations):
    assert verdict_from_observations(observations).usable is True


def test_overlaid_text_ranks_down_but_never_rejects():
    """Every false rejection in the dry run came from this one signal.

    A model cannot reliably separate branding composited onto an image from
    words that happen to be in the room, so cards and badges are caught by host
    and filename instead, where the evidence is solid.
    """
    verdict = verdict_from_observations(_seen(overlaid_text=True))

    assert verdict.usable is True
    assert verdict.has_branding is True


def test_missing_face_count_does_not_reject():
    """No opinion is not evidence against a photograph."""
    assert verdict_from_observations({"is_photograph": True, "reason": "?"}).usable is True


def test_inspection_returns_no_opinion_when_the_provider_fails(monkeypatch):
    """A provider outage must leave the stored image alone."""

    class _Client:
        async def get(self, *args, **kwargs):
            raise httpx.ConnectError("down")

        async def aclose(self):
            return None

    result = asyncio.run(
        inspect_candidate_photo(
            "https://example.com/a.jpg",
            model="test/model",
            api_key="k",
            client=_Client(),
        )
    )

    assert result is None


def test_inspection_returns_no_opinion_on_an_error_payload(monkeypatch):
    """OpenRouter reports rate limits as HTTP 200 carrying an error object."""

    class _Resp:
        content = b"\x89PNG\r\n"
        headers = {"content-type": "image/png"}

        def raise_for_status(self):
            return None

        def json(self):
            return {"error": {"message": "Rate limit exceeded"}}

    class _Client:
        async def get(self, *args, **kwargs):
            return _Resp()

        async def post(self, *args, **kwargs):
            return _Resp()

        async def aclose(self):
            return None

    result = asyncio.run(
        inspect_candidate_photo(
            "https://example.com/a.jpg",
            model="test/model",
            api_key="k",
            client=_Client(),
        )
    )

    assert result is None


def test_verdict_reports_what_was_seen():
    verdict = verdict_from_observations(_seen(faces=3, era="contemporary"))

    assert isinstance(verdict, PhotoVerdict)
    assert verdict.faces == 3
    assert verdict.era == "contemporary"


def test_a_young_candidate_is_removed_but_flagged_for_a_human():
    """The one rule here that can be wrong about a real candidate.

    Vermont sets no minimum age for governor, and a catalogue sweep flagged a
    genuine teenage candidate alongside a stock photo of a child stored for a
    Delaware race. Removal is the safe direction, but the reason has to invite
    a human to check rather than read as settled.
    """
    verdict = verdict_from_observations(_seen(subject_is_child=True))

    assert verdict.usable is False
    assert "verify" in verdict.reason
