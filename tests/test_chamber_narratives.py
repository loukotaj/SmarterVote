import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from pipeline_client.agent import chamber_narratives


@pytest.mark.asyncio
async def test_generate_chamber_analyses_calls_openrouter_for_each_chamber(monkeypatch):
    payload = {
        "narrative": "Georgia Senate and Texas Senate define the Senate path.",
        "bottom_line": "The chamber is close.",
        "why_party_favored": "The favored party has the better central seat path.",
        "opposing_party_path": "The opposition needs Georgia Senate and Texas Senate to break its way.",
        "key_uncertainty": "The uncertainty sits in the tilt and lean races.",
    }
    mock_call = AsyncMock(
        return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
    )
    monkeypatch.setattr(chamber_narratives, "_call_openrouter", mock_call)

    summaries = [
        {
            "id": "ga-senate-2026",
            "title": "Georgia Senate",
            "office": "United States Senate",
            "state": "Georgia",
            "forecast": {
                "predicted_winner_party": "Democratic",
                "win_probability": 0.57,
                "rating": "tilt_d",
                "party_probabilities": {"Democratic": 0.57, "Republican": 0.43},
            },
        },
        {
            "id": "tx-senate-2026",
            "title": "Texas Senate",
            "office": "United States Senate",
            "state": "Texas",
            "forecast": {
                "predicted_winner_party": "Republican",
                "win_probability": 0.68,
                "rating": "lean_r",
                "party_probabilities": {"Democratic": 0.32, "Republican": 0.68},
            },
        },
    ]

    analyses = await chamber_narratives.generate_chamber_analyses(summaries, model="test/model")

    assert set(analyses) == {"house", "senate", "governors"}
    assert analyses["senate"]["narrative"] == payload["narrative"]
    assert mock_call.await_count == 3
    senate_prompt = mock_call.await_args_list[0].kwargs["messages"][1]["content"]
    assert "Georgia Senate" in senate_prompt
    assert "Texas Senate" in senate_prompt
