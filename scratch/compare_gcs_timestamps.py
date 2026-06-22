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

    print("Comparing drafts/ and races/ in GCS...")

    drafts = {}
    races = {}

    blobs = bucket.list_blobs()
    for b in blobs:
        if b.name.startswith("drafts/") and b.name.endswith(".json"):
            race_id = b.name.replace("drafts/", "").replace(".json", "")
            drafts[race_id] = b.updated
        elif b.name.startswith("races/") and b.name.endswith(".json") and b.name != "races/summaries.json" and b.name != "races/chamber_forecasts.json":
            race_id = b.name.replace("races/", "").replace(".json", "")
            races[race_id] = b.updated

    print(f"Total drafts found: {len(drafts)}")
    print(f"Total published races found: {len(races)}")

    unpublished_races = []
    newer_drafts = []

    for race_id, draft_time in drafts.items():
        if race_id not in races:
            unpublished_races.append(race_id)
        elif draft_time > races[race_id]:
            newer_drafts.append(race_id)

    print(f"\nUnpublished races (in drafts but NOT in races): {len(unpublished_races)}")
    if unpublished_races:
        print(f"  First 10: {unpublished_races[:10]}")

    print(f"Newer drafts (draft is newer than published): {len(newer_drafts)}")
    if newer_drafts:
        print(f"  First 10: {newer_drafts[:10]}")

if __name__ == "__main__":
    main()
