import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from smartervote_mcp.gcp_launcher import configure_admin_key_from_gcp
from smartervote_mcp.client import RacesApiClient

async def main():
    print("Configuring GCP auth...")
    os.environ.setdefault("SMARTERVOTE_RACES_API_URL", "https://races-api-dev-ddsvfazica-uc.a.run.app")
    os.environ.setdefault("SMARTERVOTE_GCP_PROJECT", "smartervote")
    os.environ.setdefault("SMARTERVOTE_GCP_ENVIRONMENT", "dev")
    configure_admin_key_from_gcp()

    print("Creating Client...")
    client = RacesApiClient.from_env()

    print("Fetching published chamber forecasts...")
    try:
        res = await client.get("/races/chamber_forecasts")
        print("Success! Schema version:", res.get("schema_version"))
        print("Updated at:", res.get("updated_at"))
        chambers = res.get("chambers", {})
        for name, data in chambers.items():
            print(f"- Chamber: {name}")
            print(f"  Narrative: {data.get('narrative')[:80]}...")
            print(f"  Seat Distribution Count: {len(data.get('seat_distribution', {}))}")
            print(f"  Expected Seats: {data.get('expected_seats')}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
