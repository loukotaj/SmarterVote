import json
from pathlib import Path

def main():
    project_root = Path(__file__).resolve().parent.parent
    summaries_path = project_root / "data" / "published" / "summaries.json"

    if not summaries_path.exists():
        print(f"Error: summaries.json not found at {summaries_path}")
        return

    with summaries_path.open("r", encoding="utf-8") as f:
        summaries = json.load(f)

    if not isinstance(summaries, list):
        print("Error: summaries.json is not a list")
        return

    print(f"Total races in summaries.json: {len(summaries)}")

    # 1. Group by office
    senate_races = []
    governor_races = []
    house_races = []

    for r in summaries:
        office = str(r.get("office") or "").lower()
        if "senate" in office:
            senate_races.append(r)
        elif "governor" in office or "gubernatorial" in office:
            governor_races.append(r)
        elif "house" in office or "representative" in office:
            house_races.append(r)

    print(f"Senate races: {len(senate_races)}")
    print(f"Governor races: {len(governor_races)}")
    print(f"House races: {len(house_races)}")

    # 2. Audit forecasts
    for name, races in [("Senate", senate_races), ("Governor", governor_races), ("House", house_races)]:
        missing = []
        stale = []
        complete = 0

        for r in races:
            race_id = r.get("id") or r.get("race_id")
            forecast = r.get("forecast")
            if not forecast:
                missing.append(race_id)
            else:
                generated_at = forecast.get("generated_at")
                updated_utc = r.get("updated_utc")
                if generated_at and updated_utc:
                    try:
                        gen_str = generated_at.replace("Z", "").split(".")[0]
                        up_str = updated_utc.replace("Z", "").split(".")[0]
                        if gen_str < up_str:
                            stale.append(race_id)
                        else:
                            complete += 1
                    except Exception:
                        complete += 1
                else:
                    complete += 1

        print(f"\n--- {name} Forecast Audit ---")
        print(f"Total: {len(races)}")
        print(f"Complete: {complete}")
        print(f"Missing: {len(missing)}")
        if missing:
            print(f"  Missing IDs: {missing[:10]}...")
        print(f"Stale: {len(stale)}")
        if stale:
            print(f"  Stale IDs: {stale[:10]}...")

if __name__ == "__main__":
    main()
