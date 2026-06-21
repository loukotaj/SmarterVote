import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from smartervote_mcp.gcp_launcher import configure_admin_key_from_gcp
from smartervote_mcp.client import RacesApiClient
from shared.forecast_summary import _chamber_races, fallback_party_for_race, normalize_party, _race_party_probabilities

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
        forecast = r.get("forecast")
        if not forecast:
            party = fallback_party_for_race(r)
            print(f"ID: {r.get('id')} -> No forecast, fallback={party}")
            continue

        party = normalize_party(forecast.get("predicted_winner_party"))
        if party == "Other":
            probs = _race_party_probabilities(forecast)
            if probs.get("Democratic", 0.0) > probs.get("Republican", 0.0):
                party = "Democratic"
            elif probs.get("Republican", 0.0) > probs.get("Democratic", 0.0):
                party = "Republican"
            else:
                party = fallback_party_for_race(r)

        if party == "Other":
            print(f"ID: {r.get('id')} -> Resolves to OTHER!")
            print(f"  Forecast: {forecast}")
            print(f"  Fallback: {fallback_party_for_race(r)}")

if __name__ == "__main__":
    asyncio.run(main())
