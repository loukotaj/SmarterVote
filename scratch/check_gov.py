import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from smartervote_mcp.gcp_launcher import configure_admin_key_from_gcp
from smartervote_mcp.client import RacesApiClient
from shared.forecast_summary import _chamber_races, fallback_party_for_race

async def main():
    os.environ["SMARTERVOTE_RACES_API_URL"] = "https://races-api-dev-913009244252.us-central1.run.app"
    os.environ["SMARTERVOTE_GCP_PROJECT"] = "smartervote"
    os.environ["SMARTERVOTE_GCP_ENVIRONMENT"] = "dev"

    configure_admin_key_from_gcp()
    client = RacesApiClient.from_env()

    summaries = await client.get('/races/summaries')
    gov_races = _chamber_races(summaries, 'governors')

    print(f"Total Gov races: {len(gov_races)}")
    for r in gov_races:
        fc = r.get("forecast") or {}
        winner = fc.get("predicted_winner_party")
        fallback = fallback_party_for_race(r)

        # If winner is Other or fallback is Other, print it
        if winner == "Other" or fallback == "Other" or (not fc and fallback == "Other"):
            print(f"ID: {r.get('id')}")
            print(f"  Title: {r.get('title')}")
            print(f"  Winner: {winner}")
            print(f"  Fallback: {fallback}")
            print(f"  Candidates: {r.get('candidates')}")

if __name__ == "__main__":
    asyncio.run(main())
