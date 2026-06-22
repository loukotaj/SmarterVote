import os
import sys
import json
from pathlib import Path

# Add project root and services/races-api to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "services" / "races-api"))

from google.cloud import storage as gcs

def main():
    bucket_name = "smartervote-sv-data-dev"
    client = gcs.Client()
    bucket = client.bucket(bucket_name)

    print("Checking draft chamber forecasts...")
    try:
        draft_blob = bucket.blob("drafts/chamber_forecasts.json")
        if draft_blob.exists():
            draft_data = json.loads(draft_blob.download_as_text())
            print("Draft exists. Senate narrative:")
            print(draft_data.get("senate"))
            print("Draft chambers keys:", list(draft_data.get("chambers", {}).keys()))
        else:
            print("No draft chamber forecasts found in GCS.")
    except Exception as e:
        print(f"Error loading draft: {e}")

    print("\nChecking published chamber forecasts...")
    try:
        pub_blob = bucket.blob("races/chamber_forecasts.json")
        if pub_blob.exists():
            pub_data = json.loads(pub_blob.download_as_text())
            print("Published exists. Senate narrative:")
            print(pub_data.get("senate"))
        else:
            print("No published chamber forecasts found in GCS.")
    except Exception as e:
        print(f"Error loading published: {e}")

if __name__ == "__main__":
    main()
