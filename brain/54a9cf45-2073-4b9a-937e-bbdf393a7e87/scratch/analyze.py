import re

# Expected House seats per state (standard 435 districts)
expected_house = {
    "al": 7, "ak": 1, "az": 9, "ar": 4, "ca": 52, "co": 8, "ct": 5, "de": 1,
    "fl": 28, "ga": 14, "hi": 2, "id": 2, "il": 17, "in": 9, "ia": 4, "ks": 4,
    "ky": 6, "la": 6, "me": 2, "md": 8, "ma": 9, "mi": 13, "mn": 8, "ms": 4,
    "mo": 8, "mt": 2, "ne": 3, "nv": 4, "nh": 2, "nj": 12, "nm": 3, "ny": 26,
    "nc": 14, "nd": 1, "oh": 15, "ok": 5, "or": 6, "pa": 17, "ri": 2, "sc": 7,
    "sd": 1, "tn": 9, "tx": 38, "ut": 4, "vt": 1, "va": 11, "wa": 10, "wv": 2,
    "wi": 8, "wy": 1
}

# The 36 states with expected governor elections in 2026
expected_governors = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "fl", "ga", "hi", "id", "il", "ia",
    "ks", "me", "md", "ma", "mi", "mn", "ne", "nv", "nh", "nm", "ny", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "vt", "wi", "wy"
}

# Read race IDs from step 13 output
with open(r"C:\Users\jacob\.gemini\antigravity-ide\brain\54a9cf45-2073-4b9a-937e-bbdf393a7e87\.system_generated\steps\13\output.txt", "r") as f:
    race_ids = [line.strip() for line in f if line.strip()]

# Parse the 505 race IDs from list_published_races
actual_senate = []
actual_house = {}
actual_governor = []
other = []

for rid in race_ids:
    if "senate" in rid:
        actual_senate.append(rid)
    elif "governor" in rid:
        actual_governor.append(rid)
    elif "house" in rid:
        # Match pattern: state-house-2026 or state-house-01-2026 or state-01-house-2026
        # Let's extract the state
        parts = rid.split('-')
        state = parts[0]
        # Some are like az-01-house-2026 or ny-04-house-2026 or wa-01-house-2026 or or-05-house-2026
        # Let's just map the state using the first two chars or parts[0]
        # E.g., az-01-house-2026 -> parts[0] is 'az'
        # Or parts[1] is house?
        # Let's write a robust parser.
        m = re.match(r"^([a-z]{2})-(?:house|(\d+)-house|house-(\d+))", rid)
        if m:
            state = m.group(1)
            dist_str = m.group(2) or m.group(3)
            dist = int(dist_str) if dist_str else 1 # at-large is typically 1 or no district suffix
        else:
            # Let's try match: state-district-house-2026
            m2 = re.match(r"^([a-z]{2})-(\d+)-house", rid)
            if m2:
                state = m2.group(1)
                dist = int(m2.group(2))
            else:
                print(f"Unmatched house ID: {rid}")
                state = parts[0]
                dist = 1

        actual_house.setdefault(state, []).append(dist)
    else:
        other.append(rid)

# Check governors
missing_governors = expected_governors - {rid.split('-')[0] for rid in actual_governor}
extra_governors = {rid.split('-')[0] for rid in actual_governor} - expected_governors

print("--- GOVERNORS ---")
print(f"Actual governor races count: {len(actual_governor)}")
print("Expected governors count: 36")
print("Missing governors states:", sorted(list(missing_governors)))
print("Extra governors states:", sorted(list(extra_governors)))
print("Actual governors in DB:", sorted(actual_governor))

# Check house
print("\n--- HOUSE ---")
print(f"Actual house districts count: {sum(len(dists) for dists in actual_house.values())}")
print("Expected house districts count: 435")

missing_house = []
extra_house = []

for state, exp_cnt in expected_house.items():
    act_dists = actual_house.get(state, [])
    # We expect 1..exp_cnt, unless exp_cnt is 1, in which case we expect 'state-house-2026'
    # Let's check what actual IDs we have for this state
    act_ids_for_state = [rid for rid in race_ids if rid.startswith(f"{state}-") and "house" in rid]

    # Let's check which districts are missing
    if exp_cnt == 1:
        expected_ids = [f"{state}-house-2026"]
    else:
        expected_ids = [f"{state}-house-{d:02d}-2026" for d in range(1, exp_cnt + 1)]
        # Wait, some might be formatted differently, e.g., az-01-house-2026 instead of az-house-01-2026?
        # Let's inspect the database IDs to see if they match the expected patterns

    # We can match by analyzing if the actual IDs match the expected ones
    # Let's check each expected ID
    for exp_id in expected_ids:
        # Check if exp_id is in actual_ids or if there is a variant (like state-district-house-2026)
        # For example, if exp_id is az-house-01-2026, let's also check if az-01-house-2026 is in race_ids
        variant_id = None
        m_exp = re.match(r"^([a-z]{2})-house-(\d+)-2026", exp_id)
        if m_exp:
            variant_id = f"{m_exp.group(1)}-{m_exp.group(2)}-house-2026"

        if exp_id in race_ids:
            continue
        elif variant_id and variant_id in race_ids:
            continue
        else:
            missing_house.append(exp_id)

# Any actual IDs that don't map to expected ones?
for rid in race_ids:
    if "house" not in rid:
        continue
    # Let's see if this rid matches any expected ID or variant
    matched = False
    for state, exp_cnt in expected_house.items():
        if exp_cnt == 1:
            expected_ids = [f"{state}-house-2026"]
        else:
            expected_ids = [f"{state}-house-{d:02d}-2026" for d in range(1, exp_cnt + 1)]
        for exp_id in expected_ids:
            m_exp = re.match(r"^([a-z]{2})-house-(\d+)-2026", exp_id)
            variant_id = f"{m_exp.group(1)}-{m_exp.group(2)}-house-2026" if m_exp else None
            if rid == exp_id or rid == variant_id:
                matched = True
                break
        if matched:
            break
    if not matched:
        extra_house.append(rid)

print("Missing House districts:", sorted(missing_house))
print("Extra House districts:", sorted(extra_house))

# Check senate
print("\n--- SENATE ---")
print(f"Actual senate races count: {len(actual_senate)}")
print("Actual senate races:", sorted(actual_senate))
