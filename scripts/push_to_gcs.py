"""Upload local published race JSON files to Google Cloud Storage.

Usage:
    python scripts/push_to_gcs.py                     # upload all races
    python scripts/push_to_gcs.py ga-senate-2026      # upload one race
    python scripts/push_to_gcs.py --dry-run            # preview without uploading

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


def _bucket_from_terraform() -> str | None:
    """Try to get bucket name from `terraform output -raw bucket_name`."""
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


def get_races(race_ids: list[str]) -> list[Path]:
    """Return paths to the requested (or all) published race files."""
    if race_ids:
        paths = []
        for rid in race_ids:
            p = PUBLISHED_DIR / f"{rid}.json"
            if not p.exists():
                print(f"  ✗ Not found: {p}", file=sys.stderr)
            else:
                paths.append(p)
        return paths
    return sorted(PUBLISHED_DIR.glob("*.json"))


def upload(paths: list[Path], bucket_name: str, dry_run: bool) -> None:
    if not paths:
        print("No files to upload.")
        return

    if dry_run:
        print(f"[dry-run] Would upload {len(paths)} file(s) to gs://{bucket_name}/races/")
        for p in paths:
            print(f"  → gs://{bucket_name}/races/{p.stem}.json  ({p.stat().st_size // 1024} KB)")
        return

    try:
        from google.cloud import storage
    except ImportError:
        print("google-cloud-storage is not installed. Run: pip install google-cloud-storage", file=sys.stderr)
        sys.exit(1)

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    ok = 0
    for p in paths:
        try:
            blob = bucket.blob(f"races/{p.stem}.json")
            blob.upload_from_filename(str(p), content_type="application/json")
            size_kb = p.stat().st_size // 1024
            print(f"  ✓ gs://{bucket_name}/races/{p.stem}.json  ({size_kb} KB)")
            ok += 1
        except Exception as exc:
            print(f"  ✗ {p.stem}: {exc}", file=sys.stderr)

    print(f"\nUploaded {ok}/{len(paths)} file(s) to gs://{bucket_name}/races/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload local race JSON files to GCS")
    parser.add_argument("race_ids", nargs="*", metavar="RACE_ID", help="Race IDs to upload (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without uploading")
    parser.add_argument("--bucket", help="GCS bucket name (overrides GCS_BUCKET_NAME env var)")
    args = parser.parse_args()

    bucket_name = args.bucket or os.getenv("GCS_BUCKET_NAME")
    if not bucket_name:
        print("GCS_BUCKET_NAME not set — trying terraform output...", file=sys.stderr)
        bucket_name = _bucket_from_terraform()
        if bucket_name:
            print(f"  Using bucket from Terraform: {bucket_name}", file=sys.stderr)
    if not bucket_name:
        print(
            "Error: could not determine bucket name.\n"
            "  Set GCS_BUCKET_NAME in your environment/.env, pass --bucket, "
            "or run this from a directory where `terraform output bucket_name` works.",
            file=sys.stderr,
        )
        sys.exit(1)

    paths = get_races(args.race_ids)
    if not paths:
        print(f"No published races found in {PUBLISHED_DIR}")
        sys.exit(0)

    print(f"Uploading to gs://{bucket_name}/races/")
    upload(paths, bucket_name, args.dry_run)


if __name__ == "__main__":
    main()
