"""Look at a candidate photo before storing it.

Every other guard in :mod:`pipeline_client.agent.images` reasons about the URL —
its host, its filename, the dimensions a CMS baked into it. That works until the
URL carries no signal, and then it is blind. Images published live on real races
that no filename rule could ever have caught:

===========================  =========================================
stored URL                   what the picture actually was
===========================  =========================================
``Andrew_Rice.jpg``          a man in front of the Oklahoma state flag
``Mike_Nichols.jpg``         a mid-century publicity still
``11198004.jpeg``            a child in a youth baseball uniform
``jumbotron.png``            a bridge and a water tower
``StevenSwinton.png``        a map of a congressional district
===========================  =========================================

So this asks a small vision model what is in the frame. It deliberately asks
only perceptual questions — how many faces, is this a photograph, is the face
obscured — and never "is this the right person", which it cannot know. Identity
stays the URL rules' job.

**Overlaid text is measured but does not reject.** In the dry run that shaped
this module, every false rejection came from that one signal: a candidate
photographed in front of his own campaign backdrop, and a man whose t-shirt had
a business name printed on it. A model cannot reliably separate branding
composited onto an image from words that happen to be in the room. Cards and
badges are caught by host and filename instead, where the evidence is solid.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from .cost import accumulate

logger = logging.getLogger("pipeline")

#: Bigger than any portrait needs and small enough to stay cheap.
MAX_IMAGE_BYTES = 8 * 1024 * 1024

_PROMPT = """You are checking whether an image can serve as the official headshot for a
political candidate on a voter information site.

Report only what you can see. Do not guess who the person is.

Answer with JSON and nothing else:
{
  "faces": <int>,
  "is_photograph": <bool>,
  "obscured_face": <bool>,
  "subject_is_child": <bool>,
  "era": "contemporary" | "archival",
  "uniform_or_costume": <string|null>,
  "overlaid_text": <bool>,
  "reason": "<12 words max>"
}

"era" is "archival" when styling, grain or dress place the photograph before
about 1990. "uniform_or_costume" names sports kit, military dress, religious
vestments or similar, else null. "obscured_face" covers a helmet, a mask, or a
subject too distant or turned away to identify."""


@dataclass(frozen=True)
class PhotoVerdict:
    """What the model saw, and whether that disqualifies the image."""

    usable: bool
    reason: str
    faces: Optional[int] = None
    era: Optional[str] = None
    overlaid_text: bool = False

    @property
    def has_branding(self) -> bool:
        """True when the frame carries text. Ranks an image down, never out."""
        return self.overlaid_text


def _sports_kit(costume: Any) -> bool:
    text = str(costume or "").lower()
    return any(word in text for word in ("sport", "jersey", "uniform kit", "athletic"))


def verdict_from_observations(observations: dict[str, Any]) -> PhotoVerdict:
    """Turn what the model saw into a keep-or-discard decision.

    Split from the network call so the decision rule can be tuned and tested
    against captured observations without spending anything.
    """
    faces = observations.get("faces")
    faces = faces if isinstance(faces, int) else None
    era = observations.get("era") if isinstance(observations.get("era"), str) else None
    overlaid = bool(observations.get("overlaid_text"))
    said = str(observations.get("reason") or "").strip()

    def no(reason: str) -> PhotoVerdict:
        return PhotoVerdict(False, reason, faces, era, overlaid)

    if observations.get("is_photograph") is False:
        return no("not a photograph")
    if faces == 0:
        return no("no face in the image")
    if faces is not None and faces >= 2:
        return no(f"{faces} people in the image")
    if observations.get("obscured_face"):
        return no("face is obscured")
    if observations.get("subject_is_child"):
        # Kept as a rejection on child-safety grounds, but it is the one rule
        # here that can be wrong about a real candidate: Vermont sets no
        # minimum age for governor, and a sweep flagged a genuine teenage
        # candidate alongside a stock photo of a child in a baseball uniform
        # that had been stored for a Delaware race. Blanking a young
        # candidate's photo is recoverable; publishing an unrelated child's
        # face is not, so this errs toward removal and says so loudly.
        return no("subject appears to be a child - verify before restoring")
    if era == "archival":
        return no("photograph looks archival")
    if _sports_kit(observations.get("uniform_or_costume")):
        return no(f"subject is in {observations.get('uniform_or_costume')}")
    return PhotoVerdict(True, said or "usable headshot", faces, era, overlaid)


def _record_usage(body: dict[str, Any], model: str) -> None:
    """Include the direct multimodal request in the run's normal cost totals."""
    usage = body.get("usage")
    if not isinstance(usage, dict):
        accumulate(0, 0, model)
        return
    try:
        cost = float(usage["cost"]) if usage.get("cost") is not None else None
    except (TypeError, ValueError):
        cost = None
    accumulate(
        int(usage.get("prompt_tokens") or 0),
        int(usage.get("completion_tokens") or 0),
        model,
        cost_usd=cost,
    )


async def _fetch_image(url: str, client: httpx.AsyncClient) -> Optional[tuple[str, bytes]]:
    resp = await client.get(url, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    payload = resp.content
    if not payload or len(payload) > MAX_IMAGE_BYTES:
        return None
    mime = resp.headers.get("content-type", "").split(";")[0].strip()
    if not mime.startswith("image/"):
        mime = mimetypes.guess_type(url)[0] or "image/jpeg"
    return mime, payload


async def inspect_candidate_photo(
    url: str,
    *,
    model: str,
    api_key: str,
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[PhotoVerdict]:
    """Return what the model saw, or ``None`` if it could not look.

    ``None`` means "no opinion" and must be treated as such by the caller: a
    provider outage is not evidence against a photograph.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient()
    try:
        fetched = await _fetch_image(url, client)
        if fetched is None:
            return None
        mime, payload = fetched
        encoded = base64.b64encode(payload).decode()
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://smarter.vote"),
                "X-Title": os.getenv("OPENROUTER_APP_TITLE", "SmarterVote"),
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _PROMPT},
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                        ],
                    }
                ],
                "max_tokens": 400,
                "temperature": 0,
            },
            timeout=90,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("error") or not body.get("choices"):
            return None
        _record_usage(body, model)
        content = str(body["choices"][0]["message"]["content"]).strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        observations = json.loads(content)
        if not isinstance(observations, dict):
            return None
        return verdict_from_observations(observations)
    except (httpx.HTTPError, ValueError, KeyError, IndexError, json.JSONDecodeError, asyncio.TimeoutError):
        return None
    finally:
        if owns_client:
            await client.aclose()
