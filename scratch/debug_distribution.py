import os
import sys
import json
from pathlib import Path

# Add project root and services/races-api to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "services" / "races-api"))

from google.cloud import storage as gcs
from shared.forecast_summary import summarize_chamber, office_group

def main():
    bucket_name = "smartervote-sv-data-dev"
    print(f"Connecting to GCS bucket: {bucket_name}...")
    try:
        client = gcs.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob("races/summaries.json")
        summaries = json.loads(blob.download_as_text())
    except Exception as e:
        print(f"Failed to fetch summaries from GCS: {e}")
        return

    print(f"Total summaries: {len(summaries)}")

    for chamber in ("house", "senate", "governors"):
        races = [r for r in summaries if office_group(r) == chamber]
        print(f"\nChamber: {chamber}, active races: {len(races)}")

        summary = summarize_chamber(summaries, chamber)
        print(f"Expected seats: {summary.get('expected_seats')}")
        print(f"Projected seats: {summary.get('projected_seats')}")
        print(f"Seat distribution keys: {list(summary.get('seat_distribution', {}).keys())}")
        print(f"Seat distribution sum: {sum(summary.get('seat_distribution', {}).values())}")

if __name__ == "__main__":
    main()
