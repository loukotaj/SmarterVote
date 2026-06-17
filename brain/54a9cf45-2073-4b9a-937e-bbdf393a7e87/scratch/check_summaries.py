import json

# Read summaries.json
with open(r"C:\Users\jacob\Programming\SmarterVote\SmarterVote\SmarterVote\data\published\summaries.json", "r") as f:
    summaries = json.load(f)

print(f"Total race summaries in summaries.json: {len(summaries)}")
ids_in_summaries = [s["id"] for s in summaries]

# Compare with the 505 race IDs from list_published_races
with open(r"C:\Users\jacob\.gemini\antigravity-ide\brain\54a9cf45-2073-4b9a-937e-bbdf393a7e87\.system_generated\steps\13\output.txt", "r") as f:
    mcp_race_ids = [line.strip() for line in f if line.strip()]

print(f"Total race IDs from MCP server: {len(mcp_race_ids)}")

mcp_set = set(mcp_race_ids)
summaries_set = set(ids_in_summaries)

print("In MCP but not in summaries.json:", len(mcp_set - summaries_set))
print(sorted(list(mcp_set - summaries_set))[:20])
print("In summaries.json but not in MCP:", len(summaries_set - mcp_set))
print(sorted(list(summaries_set - mcp_set))[:20])
