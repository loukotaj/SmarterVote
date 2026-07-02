"""Tests for Ballotpedia election URL derivation and candidate lookup."""

import pytest

from pipeline_client.agent.ballotpedia import (
    _is_unusable_ballotpedia_html,
    _parse_candidate_list_from_html,
    _parse_wikipedia_candidate_list,
    _race_id_to_ballotpedia_district_url,
    _race_id_to_ballotpedia_url,
    _race_id_to_wikipedia_url,
    default_ballotpedia_race_url,
    lookup_candidate_data,
    lookup_election_page,
)


def test_wikipedia_url_derivation():
    assert (
        _race_id_to_wikipedia_url("ar-governor-2026") == "https://en.wikipedia.org/wiki/2026_Arkansas_gubernatorial_election"
    )
    assert (
        _race_id_to_wikipedia_url("ga-senate-2026")
        == "https://en.wikipedia.org/wiki/2026_United_States_Senate_election_in_Georgia"
    )
    assert (
        _race_id_to_wikipedia_url("oh-senate-2026-special")
        == "https://en.wikipedia.org/wiki/2026_United_States_Senate_special_election_in_Ohio"
    )
    # House races have no reliable single-article pattern → no fallback URL.
    assert _race_id_to_wikipedia_url("ar-house-03-2026") is None


def test_wikipedia_candidate_parser_scopes_to_active_nominees():
    """Parse nominees under party 'Candidates' sections; skip endorsements and
    eliminated/withdrawn entries (mirrors the real AR governor article)."""
    html = """
    <h2>Republican primary</h2>
      <h3>Candidates</h3>
        <h4>Nominee</h4>
        <ul><li>Sarah Huckabee Sanders, incumbent governor (2023-present)</li></ul>
      <h3>Endorsements</h3>
        <ul><li>Donald Trump, 47th president</li></ul>
    <h2>Democratic primary</h2>
      <h3>Candidates</h3>
        <h4>Nominee</h4>
        <ul><li>Fredrick Love, state senator</li></ul>
        <h4>Eliminated in primary</h4>
        <ul><li>Supha Xayprasith-Mays, businesswoman</li></ul>
    <h2>Libertarian primary</h2>
      <h3>Candidates</h3>
        <h4>Nominee</h4>
        <ul><li>Colt Shelby, farmer</li></ul>
    """
    result = _parse_wikipedia_candidate_list(html)
    by_name = {c["name"]: c for c in result}
    assert set(by_name) == {"Sarah Huckabee Sanders", "Fredrick Love", "Colt Shelby"}
    assert by_name["Sarah Huckabee Sanders"]["party"] == "Republican"
    assert by_name["Sarah Huckabee Sanders"]["incumbent"] is True
    assert by_name["Colt Shelby"]["party"] == "Libertarian"
    assert "Donald Trump" not in by_name  # endorsement, not a candidate
    assert "Supha Xayprasith-Mays" not in by_name  # eliminated in primary


def test_wikipedia_candidate_parser_caps_large_open_primary_rosters_but_keeps_nominees_first():
    html = """
    <h2>Republican primary</h2>
      <h3>Candidates</h3>
        <h4>Nominee</h4>
        <ul><li>Major Republican, nominee</li></ul>
        <h4>Declared</h4>
        <ul><li>Republican One, business owner</li></ul>
    <h2>Democratic primary</h2>
      <h3>Candidates</h3>
        <h4>Nominee</h4>
        <ul><li>Major Democrat, nominee</li></ul>
        <h4>Declared</h4>
    """
    for surname in (
        "Adams",
        "Baker",
        "Clark",
        "Davis",
        "Evans",
        "Franklin",
        "Garcia",
        "Harris",
        "Irwin",
        "Jones",
        "King",
        "Lewis",
    ):
        html += f"<ul><li>Democrat {surname}, activist</li></ul>"

    result = _parse_wikipedia_candidate_list(html)
    names = [candidate["name"] for candidate in result]

    assert len(result) == 10
    assert names[:2] == ["Major Republican", "Major Democrat"]
    assert all("_nominee" not in candidate for candidate in result)


def test_real_page_with_embedded_recaptcha_is_usable():
    """Regression: real Ballotpedia pages embed a hidden g-recaptcha widget and a
    <noscript> fallback; these must not flag the page as a bot challenge."""
    real_html = (
        '<html><body><div class="mw-parser-output">'
        '<div id="recaptcha-service" class="g-recaptcha"></div>'
        "<noscript>Please enable JavaScript</noscript>"
        "<p>Arkansas gubernatorial election content</p></div></body></html>"
    )
    assert _is_unusable_ballotpedia_html(real_html) is False


def test_bot_challenge_page_without_content_is_unusable():
    challenge = "<html><body>Please complete the captcha to verify you are not a robot.</body></html>"
    assert _is_unusable_ballotpedia_html(challenge) is True
    assert _is_unusable_ballotpedia_html("") is True


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


def test_candidate_parser_excludes_election_history_section():
    """Prior-cycle voteboxes under an 'Election history' section must be ignored."""
    html = """
    <h4>General election</h4>
    <div class="votebox">
      <tr class="results_row "><td class="votebox-results-cell--text">
        <a href="https://ballotpedia.org/Tom_Cotton">Tom Cotton</a></td></tr>
      <tr class="results_row "><td class="votebox-results-cell--text">
        <a href="https://ballotpedia.org/Hallie_Shoffner">Hallie Shoffner</a></td></tr>
    </div>
    <h2><span class="mw-headline" id="Election_history">Election history</span></h2>
    <h3>2022</h3>
    <h4>General election</h4>
    <div class="votebox">
      <tr class="results_row "><td class="votebox-results-cell--text">
        <a href="https://ballotpedia.org/John_Boozman">John Boozman</a></td></tr>
      <tr class="results_row "><td class="votebox-results-cell--text">
        <a href="https://ballotpedia.org/Natalie_James">Natalie James</a></td></tr>
    </div>
    """
    names = [c["name"] for c in _parse_candidate_list_from_html(html)]
    assert "Tom Cotton" in names and "Hallie Shoffner" in names
    assert "John Boozman" not in names and "Natalie James" not in names


def test_candidate_parser_excludes_state_scoped_election_history_section():
    """Ballotpedia often scopes the history anchor to the state (e.g.
    id="Texas_U.S._Senate_election_history") rather than the plain
    id="Election_history". Prior-cycle voteboxes under such anchors must also be
    cut so off-cycle names (e.g. a 2018/2024 nominee) never enter the roster."""
    html = """
    <h4>General election</h4>
    <div class="votebox">
      <tr class="results_row "><td class="votebox-results-cell--text">
        <a href="https://ballotpedia.org/John_Cornyn">John Cornyn</a></td></tr>
    </div>
    <h2><span class="mw-headline" id="Texas_U.S._Senate_election_history">Texas U.S. Senate election history</span></h2>
    <h3>2018</h3>
    <h4>General election</h4>
    <div class="votebox">
      <tr class="results_row "><td class="votebox-results-cell--text">
        <a href="https://ballotpedia.org/Ted_Cruz">Ted Cruz</a></td></tr>
      <tr class="results_row "><td class="votebox-results-cell--text">
        <a href="https://ballotpedia.org/Beto_ORourke">Beto O'Rourke</a></td></tr>
    </div>
    """
    names = [c["name"] for c in _parse_candidate_list_from_html(html)]
    assert "John Cornyn" in names
    assert "Ted Cruz" not in names and "Beto O'Rourke" not in names


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
