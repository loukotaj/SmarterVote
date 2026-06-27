"""Tests for Ballotpedia election URL derivation and candidate lookup."""

import pytest

from pipeline_client.agent.ballotpedia import (
    _parse_candidate_list_from_html,
    _race_id_to_ballotpedia_district_url,
    _race_id_to_ballotpedia_url,
    default_ballotpedia_race_url,
    lookup_candidate_data,
    lookup_election_page,
)


def test_governor_race_uses_state_gubernatorial_url():
    assert _race_id_to_ballotpedia_url("ga-governor-2026") == "https://ballotpedia.org/Georgia_gubernatorial_election,_2026"


def test_senate_race_url_still_uses_senate_pattern():
    assert (
        _race_id_to_ballotpedia_url("ga-senate-2026")
        == "https://ballotpedia.org/United_States_Senate_election_in_Georgia,_2026"
    )


def test_house_race_uses_possessive_congressional_district_urls():
    assert (
        _race_id_to_ballotpedia_url("ar-house-03-2026")
        == "https://ballotpedia.org/Arkansas'_3rd_Congressional_District_election,_2026"
    )
    assert (
        _race_id_to_ballotpedia_district_url("ar-house-03-2026")
        == "https://ballotpedia.org/Arkansas'_3rd_Congressional_District"
    )
    assert default_ballotpedia_race_url("ar-house-03-2026") == "https://ballotpedia.org/Arkansas'_3rd_Congressional_District"


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


def test_candidate_parser_keeps_only_winners_from_completed_primary_sections():
    html = """
    <h4>Democratic primary election</h4>
    <div class="votebox">
      <tr class="results_row winner"><td class="votebox-results-cell--text">
        <a href="https://ballotpedia.org/Winner_Candidate">Winner Candidate</a>
      </td></tr>
      <tr class="results_row"><td class="votebox-results-cell--text">
        <a href="https://ballotpedia.org/Losing_Candidate">Losing Candidate</a>
      </td></tr>
    </div>
    """

    assert _parse_candidate_list_from_html(html) == [{"name": "Winner Candidate", "party": "Democratic", "incumbent": False}]


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
    def __init__(self, url: str, text: str, status_code: int = 200):
        self.url = url
        self.text = text
        self.status_code = status_code


@pytest.mark.asyncio
async def test_ballotpedia_lookup_uses_proxy_for_blocked_candidate_page(monkeypatch):
    monkeypatch.setattr("pipeline_client.agent.ballotpedia.httpx.AsyncClient", _FakeBallotpediaClient)

    result = await lookup_candidate_data("Roy Cooper")

    assert result["found"] is True
    assert result["page_url"] == "https://ballotpedia.org/Roy_Cooper"
    assert result["image_url"] == "https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/Roy_Cooper.jpg"


class _FakeElectionFallbackClient:
    def __init__(self, *args, **kwargs):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, **kwargs):
        self.calls.append(url)
        if "Congressional_District_election" in url:
            return _FakeResponse(url=url, text="blocked", status_code=451)
        if "Congressional_District" in url:
            return _FakeResponse(
                url=url,
                text="""
                <div id="mw-parser-output"><p>District page with candidate table.</p></div>
                <h4>Democratic primary election</h4>
                <div class="votebox">
                  <tr class="results_row"><td class="votebox-results-cell--text">
                    <a href="https://ballotpedia.org/Jane_Doe">Jane Doe</a>
                  </td></tr>
                </div>
                """,
            )
        return _FakeResponse(url=url, text="", status_code=404)


@pytest.mark.asyncio
async def test_election_lookup_fetches_district_fallback_when_generated_url_fails(monkeypatch):
    fake_client = _FakeElectionFallbackClient()
    monkeypatch.setattr("pipeline_client.agent.ballotpedia.httpx.AsyncClient", lambda *args, **kwargs: fake_client)

    result = await lookup_election_page("ca-house-06-2026")

    assert result["found"] is True
    assert result["page_url"] == "https://ballotpedia.org/California's_6th_Congressional_District"
    assert result["candidates"] == [{"name": "Jane Doe", "party": "Democratic", "incumbent": False}]
    assert any("Congressional_District_election" in call for call in fake_client.calls)
    assert any(call.endswith("Congressional_District") for call in fake_client.calls)
