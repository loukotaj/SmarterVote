import os
import sys

sys.path.append("c:/Users/jacob/Programming/SmarterVote/SmarterVote/SmarterVote")
sys.path.append("c:/Users/jacob/Programming/SmarterVote/SmarterVote/SmarterVote/services/races-api")

from google.cloud import firestore

db = firestore.Client()
docs = db.collection("pipeline_queue").stream()
active = []
for doc in docs:
    d = doc.to_dict() or {}
    if d.get("status") in ("pending", "running"):
        active.append(d)

print(f"Active items count: {len(active)}")
for idx, a in enumerate(active):
    print(f"{idx+1}. Race: {a.get('race_id')} | Status: {a.get('status')} | Created: {a.get('created_at')} | Run ID: {a.get('run_id')}")
