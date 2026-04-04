import asyncio
import sys

sys.path.insert(0, ".")
from pipeline_client.agent.ballotpedia import lookup_candidate_data


async def test():
    for name in ["Tom Cotton", "Hallie Shoffner", "Nonexistent Person XYZ"]:
        result = await lookup_candidate_data(name)
        print(
            f"{name}: found={result.get('found')}, image={result.get('image_url', '')[:60]}, page={result.get('page_url', '')[:60]}"
        )
        if result.get("extract"):
            print(f"  extract: {result['extract'][:120]}")
        if result.get("external_links"):
            print(f"  links ({len(result['external_links'])}): {result['external_links'][:2]}")


asyncio.run(test())
