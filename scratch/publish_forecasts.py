import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from smartervote_mcp.gcp_launcher import configure_admin_key_from_gcp, configure_cloud_run_identity_token_from_gcp
from smartervote_mcp.client import RacesApiClient

async def main():
    print("Configuring GCP auth...")
    # Set default environment variables as MCP configuration does
    os.environ.setdefault("SMARTERVOTE_RACES_API_URL", "https://races-api-dev-ddsvfazica-uc.a.run.app")
    os.environ.setdefault("SMARTERVOTE_GCP_PROJECT", "smartervote")
    os.environ.setdefault("SMARTERVOTE_GCP_ENVIRONMENT", "dev")
    os.environ.setdefault("SMARTERVOTE_RACES_API_USE_CLOUD_RUN_ID_TOKEN", "true")

    configure_admin_key_from_gcp()

    print("Creating Races API Client...")
    client = RacesApiClient.from_env()
    print(f"API Base URL: {client.base_url}")
    print(f"Admin Key exists: {bool(client.admin_key)}")
    print(f"Cloud Run Identity Token exists: {bool(client.cloud_run_id_token)}")

    print("Publishing chamber forecasts...")
    try:
        res = await client.post("/api/races/chamber_forecasts/publish")
        print("Success!")
        print(res)
    except Exception as e:
        print(f"Failed to publish: {e}")

if __name__ == "__main__":
    asyncio.run(main())
