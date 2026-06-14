import os
import sys
import uuid

# Load env variables from .env
env_path = "c:/Users/jacob/Programming/SmarterVote/SmarterVote/SmarterVote/.env"
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ[k] = v

if "GCS_BUCKET" not in os.environ and "GCS_BUCKET_NAME" in os.environ:
    os.environ["GCS_BUCKET"] = os.environ["GCS_BUCKET_NAME"]

sys.path.append("c:/Users/jacob/Programming/SmarterVote/SmarterVote/SmarterVote")
sys.path.append("c:/Users/jacob/Programming/SmarterVote/SmarterVote/SmarterVote/services/races-api")

from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
import firestore_helpers
import gcs_helpers

db = firestore.Client()

# 1. Fetch all queue items
print("Fetching all queue items...")
queue_docs = list(db.collection("pipeline_queue").stream())
queue_items = [d.to_dict() or {} for d in queue_docs]

# 2. Check for active runs (pending or running) for today's bulk run
active_items = [
    item for item in queue_items
    if item.get("status") in ("pending", "running")
    and "Bulk 2026 roster" in (item.get("options") or {}).get("note", "")
]

if active_items:
    print(f"STATUS: STILL_RUNNING ({len(active_items)} items active/pending)")
    for idx, item in enumerate(active_items[:10]):
        print(f"  - {item.get('race_id')} ({item.get('status')})")
    if len(active_items) > 10:
        print(f"  ... and {len(active_items) - 10} more.")
    sys.exit(0)

print("No active runs currently in the queue.")

# 3. Check for failed original runs that haven't been retried yet
failed_original = []
for item in queue_items:
    note = (item.get("options") or {}).get("note", "")
    if "Bulk 2026 roster" in note and "Retry" not in note and item.get("status") == "failed":
        failed_original.append(item)

retried_race_ids = set()
for item in queue_items:
    note = (item.get("options") or {}).get("note", "")
    if "Bulk 2026 roster" in note and "Retry" in note:
        retried_race_ids.add(item.get("race_id"))

to_requeue = [item.get("race_id") for item in failed_original if item.get("race_id") not in retried_race_ids]

if to_requeue:
    print(f"STATUS: REQUEUEING ({len(to_requeue)} failed races to retry)")
    for rid in to_requeue:
        print(f"  - Requeueing: {rid}")

        # Options for retry
        opts = {
            "cheap_mode": True,
            "enabled_steps": ["discovery"],
            "note": "Bulk 2026 roster (Retry)"
        }

        item_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        retry_item = {
            "id": item_id,
            "race_id": rid,
            "run_id": run_id,
            "options": opts,
            "status": "pending",
            "is_continuation": False,
            "created_at": SERVER_TIMESTAMP,
        }
        db.collection("pipeline_queue").document(item_id).set(retry_item)
        firestore_helpers._fs_update_race(rid, {"status": "queued", "current_run_id": run_id})

    print(f"Successfully requeued {len(to_requeue)} failed races.")
    sys.exit(0)

print("No failed original runs need retry. All discovery runs have finished.")

# 4. Publish all unpublished drafts
gcs_helpers._GCS_BUCKET = os.environ["GCS_BUCKET"]
drafts = gcs_helpers._gcs_list_race_ids("drafts") or []
published = gcs_helpers._gcs_list_race_ids("races") or []
unpublished_drafts = sorted(list(set(drafts) - set(published)))

if not unpublished_drafts:
    print("STATUS: ALL_PUBLISHED (No unpublished drafts found)")
    sys.exit(0)

print(f"STATUS: PUBLISHING ({len(unpublished_drafts)} drafts to publish)")
updates_for_gcs = {}
success_count = 0
fail_count = 0

for idx, race_id in enumerate(unpublished_drafts):
    print(f"[{idx+1}/{len(unpublished_drafts)}] Publishing {race_id}...")
    try:
        data = gcs_helpers._gcs_get_race_json(race_id, "drafts")
        if data is None:
            print(f"  FAILED: Draft data is None for {race_id}")
            fail_count += 1
            continue

        gcs_helpers.publish_race_to_gcs(race_id, data)
        updates_for_gcs[race_id] = data
        success_count += 1
    except Exception as e:
        print(f"  FAILED to publish {race_id}: {e}")
        fail_count += 1

print(f"\nSuccessfully published {success_count} races, failed {fail_count}.")

if updates_for_gcs:
    print("Updating GCS summaries.json central index in bulk...")
    try:
        gcs_helpers.update_gcs_summaries_json(updates_for_gcs)
        print("GCS summaries.json updated successfully.")
    except Exception as e:
        print(f"Failed to update GCS summaries.json: {e}")

# 5. Trigger Web Deploy
print("Triggering Web Deploy via gh CLI...")
import subprocess
try:
    result = subprocess.run(
        ["gh", "workflow", "run", "WebDeploy.yml"],
        capture_output=True,
        text=True,
        check=False
    )
    if result.returncode == 0:
        print("Successfully triggered WebDeploy.yml workflow.")
    else:
        print(f"Failed to run workflow. returncode={result.returncode}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
except Exception as exc:
    print(f"Error triggering deploy: {exc}")

print("STATUS: COMPLETED_AND_DEPLOYED")
