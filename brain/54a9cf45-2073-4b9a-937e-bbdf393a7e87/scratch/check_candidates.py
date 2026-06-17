import urllib.request
import json

url = "https://races-api-dev-ddsvfazica-uc.a.run.app/races/summaries"
print(f"Fetching from {url}...")
try:
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    )
    with urllib.request.urlopen(req) as response:
        content = response.read()
        summaries = json.loads(content)
        print(f"Total summaries: {len(summaries)}")

        # Count candidates
        zero_candidate_races = []
        one_candidate_races = []
        for s in summaries:
            candidates = s.get("candidates", [])
            if not candidates:
                zero_candidate_races.append(s)
            elif len(candidates) == 1:
                one_candidate_races.append(s)

        print(f"Races with 0 candidates: {len(zero_candidate_races)}")
        for r in zero_candidate_races:
            print(f"  ID: {r['id']} | Title: {r['title']} | Office: {r['office']}")

        print(f"Races with 1 candidate: {len(one_candidate_races)}")
        for r in one_candidate_races[:10]:
            print(f"  ID: {r['id']} | Title: {r['title']} | Office: {r['office']}")

except Exception as e:
    print("Error:", e)
