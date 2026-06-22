import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root and services/races-api to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "services" / "races-api"))

from google.cloud import storage as gcs
from pipeline_client.agent.chamber_narratives import generate_chamber_analyses
from shared.forecast_summary import build_chamber_forecasts


async def build_forecast_data(summaries, *, model: str, use_ai: bool):
    if not use_ai:
        return build_chamber_forecasts(summaries)
    analyses = await generate_chamber_analyses(summaries, model=model)
    return build_chamber_forecasts(
        summaries,
        {chamber: analysis["narrative"] for chamber, analysis in analyses.items()},
        analyses,
    )


async def main():
    parser = argparse.ArgumentParser(description="Generate and publish static chamber forecasts to GCS.")
    parser.add_argument("--bucket", default="smartervote-sv-data-dev")
    parser.add_argument("--model", default="google/gemini-2.5-flash")
    parser.add_argument("--no-ai", action="store_true", help="Use deterministic fallback narratives instead of OpenRouter.")
    args = parser.parse_args()

    bucket_name = "smartervote-sv-data-dev"
    bucket_name = args.bucket
    os.environ["GCS_BUCKET"] = bucket_name

    print(f"Connecting to GCS bucket: {bucket_name}...")
    try:
        client = gcs.Client()
        bucket = client.bucket(bucket_name)
    except Exception as e:
        print(f"Failed to connect to GCS: {e}")
        return

    # 1. Fetch published summaries
    print("Loading published summaries...")
    try:
        blob = bucket.blob("races/summaries.json")
        summaries = json.loads(blob.download_as_text())
    except Exception as e:
        print(f"Failed to load summaries: {e}")
        return

    # 2. Build chamber forecasts using local workspace code
    print("Generating chamber forecasts...")
    try:
        forecast_data = await build_forecast_data(summaries, model=args.model, use_ai=not args.no_ai)
        print("Success! Generated chamber forecasts.")
    except Exception as e:
        print(f"Failed to build chamber forecasts: {e}")
        return

    # 3. Write locally to data/published/chamber_forecasts.json
    local_path = project_root / "data" / "published" / "chamber_forecasts.json"
    print(f"Writing local file to {local_path}...")
    local_path.write_text(json.dumps(forecast_data, indent=2) + "\n", encoding="utf-8")

    # 4. Upload to GCS drafts/chamber_forecasts.json
    print("Uploading draft/chamber_forecasts.json to GCS...")
    try:
        draft_blob = bucket.blob("drafts/chamber_forecasts.json")
        draft_blob.upload_from_string(json.dumps(forecast_data, indent=2), content_type="application/json")
        print("Draft uploaded.")
    except Exception as e:
        print(f"Failed to upload draft: {e}")

    # 5. Upload to GCS races/chamber_forecasts.json
    print("Uploading races/chamber_forecasts.json to GCS...")
    try:
        pub_blob = bucket.blob("races/chamber_forecasts.json")
        pub_blob.upload_from_string(json.dumps(forecast_data, indent=2), content_type="application/json")
        print("Published file uploaded.")
    except Exception as e:
        print(f"Failed to upload published: {e}")

    print("\nAll operations completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
