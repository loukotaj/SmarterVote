import urllib.request
import json

url = "https://races-api-dev-ddsvfazica-uc.a.run.app/races/summaries"

print(f"Fetching from {url}...")
try:
    with urllib.request.urlopen(url) as response:
        content = response.read()
        data = json.loads(content)
        print(f"Success! Found {len(data)} races in production API summaries.")
        prod_ids = [r["id"] for r in data]

        # Load the 505 race IDs from MCP
        with open(r"C:\Users\jacob\.gemini\antigravity-ide\brain\54a9cf45-2073-4b9a-937e-bbdf393a7e87\.system_generated\steps\13\output.txt", "r") as f:
            mcp_race_ids = [line.strip() for line in f if line.strip()]

        mcp_set = set(mcp_race_ids)
        prod_set = set(prod_ids)

        print("In MCP but not in Prod API:", len(mcp_set - prod_set))
        print(sorted(list(mcp_set - prod_set)))
        print("In Prod API but not in MCP:", len(prod_set - mcp_set))
        print(sorted(list(prod_set - mcp_set)))
except Exception as e:
    print("Error:", e)
