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

# The 33 Class 2 Senate states in 2026
class2_senate_states = {
    "al", "ak", "ar", "co", "de", "ga", "id", "il", "ia", "ks", "ky", "la", "me",
    "ma", "mi", "mn", "ms", "mt", "ne", "nh", "nj", "nm", "nc", "ok", "or", "ri",
    "sc", "sd", "tn", "tx", "va", "wv", "wy"
}

# The 36 states with expected governor elections in 2026
expected_governors = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "fl", "ga", "hi", "id", "il", "ia",
    "ks", "me", "md", "ma", "mi", "mn", "ne", "nv", "nh", "nm", "ny", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "vt", "wi", "wy"
}

# Generate expected 506 IDs
expected_ids = set()

# 1. House (435)
for state, count in expected_house.items():
    if count == 1:
        # At large
        expected_ids.add(f"{state}-house-2026")
    else:
        for d in range(1, count + 1):
            expected_ids.add(f"{state}-house-{d:02d}-2026")

# 2. Senate (33 regular + 2 special = 35)
for state in class2_senate_states:
    expected_ids.add(f"{state}-senate-2026")
expected_ids.add("fl-senate-2026-special")
expected_ids.add("oh-senate-2026-special")

# 3. Governors (36)
for state in expected_governors:
    expected_ids.add(f"{state}-governor-2026")

print(f"Total expected IDs generated: {len(expected_ids)}")

# Load the 505 race IDs from MCP
with open(r"C:\Users\jacob\.gemini\antigravity-ide\brain\54a9cf45-2073-4b9a-937e-bbdf393a7e87\.system_generated\steps\13\output.txt", "r") as f:
    mcp_race_ids = [line.strip() for line in f if line.strip()]

mcp_set = set(mcp_race_ids)

# Let's map any variant formatting (e.g. az-01-house-2026 vs az-house-01-2026)
normalized_mcp_set = set()
raw_to_norm = {}
for rid in mcp_set:
    import re
    # Match state-district-house-2026 (like az-01-house-2026)
    m = re.match(r"^([a-z]{2})-(\d+)-house-2026$", rid)
    if m:
        norm = f"{m.group(1)}-house-{int(m.group(2)):02d}-2026"
        normalized_mcp_set.add(norm)
        raw_to_norm[rid] = norm
    else:
        normalized_mcp_set.add(rid)
        raw_to_norm[rid] = rid

# Check missing and extra using normalized sets
missing_from_mcp = expected_ids - normalized_mcp_set
extra_in_mcp = normalized_mcp_set - expected_ids

print("\nMissing from database (out of the expected 506):")
print(sorted(list(missing_from_mcp)))

print("\nExtra in database (not in the expected 506):")
# Show extra in their raw/original names if possible, or normalized
print(sorted(list(extra_in_mcp)))
