"""Download published race JSON files from Google Cloud Storage to data/published/.

Usage:
    python scripts/pull_from_gcs.py                     # sync all races from bucket
    python scripts/pull_from_gcs.py ga-senate-2026      # download one race
    python scripts/pull_from_gcs.py --dry-run            # preview without downloading

Bucket name resolution (first match wins):
    1. --bucket flag
    2. GCS_BUCKET_NAME env var (or .env file)
    3. `terraform output -raw bucket_name` (run from infra/ directory)

Requires:
    - google-cloud-storage: pip install google-cloud-storage
    - GCP credentials (Application Default Credentials or GOOGLE_APPLICATION_CREDENTIALS)
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Load .env if present
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

PUBLISHED_DIR = Path(__file__).resolve().parents[1] / "data" / "published"
INFRA_DIR = Path(__file__).resolve().parents[1] / "infra"
GCS_PREFIX = "races/"


def _bucket_from_terraform() -> str | None:
    if not INFRA_DIR.exists():
        return None
    try:
        result = subprocess.run(
            ["terraform", "output", "-raw", "bucket_name"],
            cwd=INFRA_DIR,
            capture_output=True,
            text=True,
            timeout=15,
        )
        name = result.stdout.strip()
        if result.returncode == 0 and name:
            return name
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def resolve_bucket(override: str | None) -> str:
    name = override or os.getenv("GCS_BUCKET_NAME") or _bucket_from_terraform()
    if not name:
        sys.exit(
            "ERROR: Could not determine bucket name.\n"
            "Set GCS_BUCKET_NAME in .env, pass --bucket, or run from a directory "
            "with a Terraform state that has `bucket_name` output."
        )
    return name


def main():
    parser = argparse.ArgumentParser(description="Pull published races from GCS to data/published/")
    parser.add_argument("race_ids", nargs="*", help="Race IDs to download (omit for all)")
    parser.add_argument("--bucket", help="GCS bucket name (overrides env/terraform)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without writing files")
    args = parser.parse_args()

    try:
        from google.cloud import storage
    except ImportError:
        sys.exit("ERROR: google-cloud-storage is not installed.\nRun: pip install google-cloud-storage")

    bucket_name = resolve_bucket(args.bucket)
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    # List blobs in the races/ prefix
    blobs = [b for b in bucket.list_blobs(prefix=GCS_PREFIX) if b.name.endswith(".json")]

    if not blobs:
        print(f"No race JSON files found in gs://{bucket_name}/{GCS_PREFIX}")
        return

    # Filter to requested race IDs if specified
    if args.race_ids:
        requested = {r.lower().strip() for r in args.race_ids}
        blobs = [b for b in blobs if b.name[len(GCS_PREFIX) : -len(".json")] in requested]
        if not blobs:
            sys.exit(f"ERROR: None of the requested race IDs found in bucket: {args.race_ids}")

    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    errors = 0

    for blob in blobs:
        race_id = blob.name[len(GCS_PREFIX) : -len(".json")]
        local_path = PUBLISHED_DIR / f"{race_id}.json"

        # Check if local file is already up-to-date via etag/generation
        if local_path.exists():
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    local_data = json.load(f)
                local_updated = local_data.get("updated_utc", "")
                # Re-fetch blob metadata to compare
                blob.reload()
                remote_updated = ""
                try:
                    remote_data = json.loads(blob.download_as_text())
                    remote_updated = remote_data.get("updated_utc", "")
                except Exception:
                    remote_data = None

                if remote_data and local_updated and remote_updated and local_updated == remote_updated:
                    print(f"  [skip]     {race_id}  (up to date)")
                    skipped += 1
                    continue

                # Write the already-fetched remote data
                if args.dry_run:
                    print(f"  [dry-run]  {race_id}  (would update)")
                else:
                    with open(local_path, "w", encoding="utf-8") as f:
                        json.dump(remote_data, f, indent=2, ensure_ascii=False)
                    print(f"  [updated]  {race_id}")
                    downloaded += 1
                continue
            except Exception as exc:
                print(f"  [warn]     {race_id}  failed to compare, re-downloading ({exc})")

        # Fresh download
        if args.dry_run:
            print(f"  [dry-run]  {race_id}  (would download)")
            continue

        try:
            content = blob.download_as_text()
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  [new]      {race_id}")
            downloaded += 1
        except Exception as exc:
            print(f"  [error]    {race_id}  {exc}")
            errors += 1

    print()
    if args.dry_run:
        print(f"Dry run complete — {len(blobs)} race(s) would be processed.")
    else:
        print(f"Done — {downloaded} downloaded/updated, {skipped} already up to date, {errors} errors.")
        print(f"Local folder: {PUBLISHED_DIR}")


if __name__ == "__main__":
    main()
