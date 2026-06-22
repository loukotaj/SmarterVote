import os
import sys
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

    print("Listing blobs in drafts/ ...")
    try:
        blobs = list(bucket.list_blobs(prefix="drafts/"))
        print(f"Total blobs in drafts/: {len(blobs)}")
        for blob in blobs[:10]:
            print(f"  {blob.name} (size: {blob.size} bytes)")
        if len(blobs) > 10:
            print("  ...")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
