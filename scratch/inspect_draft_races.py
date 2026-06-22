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

    test_races = ["ak-senate-2026", "ga-senate-2026"]

    for r_id in test_races:
        print(f"\n=================== INSPECTING {r_id} ===================")
        try:
            draft_blob = bucket.blob(f"drafts/{r_id}.json")
            draft_data = json.loads(draft_blob.download_as_text())
            print(f"DRAFT UPDATED: {draft_blob.updated}")
            draft_fc = draft_data.get("forecast", {})
            print("DRAFT FORECAST rating/winner/win_prob:")
            print(f"  {draft_fc.get('rating')} | {draft_fc.get('predicted_winner_party')} | {draft_fc.get('win_probability')}")
            print("DRAFT TAKEAWAY:")
            print(f"  {draft_fc.get('takeaway')}")
        except Exception as e:
            print(f"Error loading draft: {e}")

        try:
            pub_blob = bucket.blob(f"races/{r_id}.json")
            pub_data = json.loads(pub_blob.download_as_text())
            print(f"\nPUBLISHED UPDATED: {pub_blob.updated}")
            pub_fc = pub_data.get("forecast", {})
            print("PUBLISHED FORECAST rating/winner/win_prob:")
            print(f"  {pub_fc.get('rating')} | {pub_fc.get('predicted_winner_party')} | {pub_fc.get('win_probability')}")
            print("PUBLISHED TAKEAWAY:")
            print(f"  {pub_fc.get('takeaway')}")
        except Exception as e:
            print(f"Error loading published: {e}")

if __name__ == "__main__":
    main()
