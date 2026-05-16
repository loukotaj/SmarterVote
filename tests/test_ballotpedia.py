"""Tests for Ballotpedia election URL derivation."""

from pipeline_client.agent.ballotpedia import _parse_candidate_list_from_html, _race_id_to_ballotpedia_url


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
