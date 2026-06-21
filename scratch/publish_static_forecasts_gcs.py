import os
import sys
import json
from pathlib import Path

# Add project root and services/races-api to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "services" / "races-api"))

from google.cloud import storage as gcs
from shared.forecast_summary import build_chamber_forecasts

def main():
    bucket_name = "smartervote-sv-data-dev"
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
        forecast_data = build_chamber_forecasts(summaries)
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
    main()
