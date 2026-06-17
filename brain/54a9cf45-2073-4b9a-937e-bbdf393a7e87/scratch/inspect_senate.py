import json
import os

published_dir = r"C:\Users\jacob\Programming\SmarterVote\SmarterVote\SmarterVote\data\published"
senate_files = [f for f in os.listdir(published_dir) if "senate" in f and f.endswith(".json")]

print(f"Found {len(senate_files)} senate files in data/published/")

for fname in sorted(senate_files):
    path = os.path.join(published_dir, fname)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"File: {fname} | Title: {data.get('title')} | Office: {data.get('office')} | Jurisdiction: {data.get('jurisdiction')}")
