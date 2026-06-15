import os
from google.cloud import firestore

project = os.getenv("FIRESTORE_PROJECT") or os.getenv("PROJECT_ID") or "smartervote"
db = firestore.Client(project=project)

def print_last_logs(run_id):
    print(f"=== Logs for Run {run_id} ===")
    docs = db.collection("pipeline_runs").document(run_id).collection("logs").stream()
    logs = [d.to_dict() for d in docs]

    # Sort logs manually in case timestamp format varies
    def log_sort_key(entry):
        ts = entry.get("timestamp") or ""
        return ts

    logs.sort(key=log_sort_key)
    print(f"Total log entries: {len(logs)}")
    for log in logs[-100:]:
        print(f"{log.get('timestamp')} [{log.get('level', '').upper()}] {log.get('message')}")

print_last_logs("0c48319a-2f3e-4c5d-84c8-2cffdf0281c3")
print("\n")
print_last_logs("82b44ef6-281b-4e65-9277-8a7e9bc6a4ec")
