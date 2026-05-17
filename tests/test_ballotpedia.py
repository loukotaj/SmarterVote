"""Tests for Ballotpedia election URL derivation and candidate lookup."""

import pytest

from pipeline_client.agent.ballotpedia import (
    _parse_candidate_list_from_html,
    _race_id_to_ballotpedia_url,
    lookup_candidate_data,
)


def test_governor_race_uses_state_gubernatorial_url():
    assert _race_id_to_ballotpedia_url("ga-governor-2026") == "https://ballotpedia.org/Georgia_gubernatorial_election,_2026"


def test_senate_race_url_still_uses_senate_pattern():
    assert (
        _race_id_to_ballotpedia_url("ga-senate-2026")
        == "https://ballotpedia.org/United_States_Senate_election_in_Georgia,_2026"
    )


def test_candidate_parser_uses_current_primary_votebox_sections():
    html = """
    <table><tr><td><a href="/Nathan_Deal">Nathan Deal</a></td><td>Republican incumbent</td></tr></table>
    <h4>Democratic primary election</h4>
    <div class="votebox">
      <tr class="results_row "><td class="votebox-results-cell--text">
        <a href="https://ballotpedia.org/Keisha_Lance_Bottoms">Keisha Bottoms</a>
      </td></tr>
    </div>
    <h4>Withdrawn or disqualified candidates</h4>
    <ul><li><a href="https://ballotpedia.org/Ruwa_Romman">Ruwa Romman</a> (D)</li></ul>
    <h4>Republican primary election</h4>
    <div class="votebox">
      <tr class="results_row "><td class="votebox-results-cell--text">
        <a href="https://ballotpedia.org/Chris_Carr_(Georgia)">Chris Carr</a>
      </td></tr>
    </div>
    """

    assert _parse_candidate_list_from_html(html) == [
        {"name": "Keisha Lance Bottoms", "party": "Democratic", "incumbent": False},
        {"name": "Chris Carr", "party": "Republican", "incumbent": False},
    ]


class _FakeBallotpediaClient:
    def __init__(self, *args, **kwargs):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, **kwargs):
        self.calls.append(url)
        if url.startswith("https://r.jina.ai/"):
            return _FakeResponse(
                url="https://r.jina.ai/https://ballotpedia.org/Roy_Cooper",
                text="""
                # Roy Cooper

                ![](https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/Roy_Cooper.jpg)

                Roy Cooper (Democratic Party) is running for election to the U.S. Senate.
                """,
            )
        return _FakeResponse(
            url="https://ballotpedia.org/Roy_Cooper",
            text="In order to continue, we need to verify that you're not a robot. Enable JavaScript.",
        )


class _FakeResponse:
    status_code = 200

    def __init__(self, url: str, text: str):
        self.url = url
        self.text = text


@pytest.mark.asyncio
async def test_ballotpedia_lookup_uses_proxy_for_blocked_candidate_page(monkeypatch):
    monkeypatch.setattr("pipeline_client.agent.ballotpedia.httpx.AsyncClient", _FakeBallotpediaClient)

    result = await lookup_candidate_data("Roy Cooper")

    assert result["found"] is True
    assert result["page_url"] == "https://ballotpedia.org/Roy_Cooper"
    assert result["image_url"] == "https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/Roy_Cooper.jpg"
