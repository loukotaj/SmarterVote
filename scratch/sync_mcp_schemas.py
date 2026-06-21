import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from smartervote_mcp.server import mcp

async def main():
    mcp_dir = Path(os.path.expanduser("~")) / ".gemini" / "antigravity-ide" / "mcp" / "smartervote-races"
    if not mcp_dir.exists():
        print(f"Schema directory {mcp_dir} does not exist. Creating it...")
        mcp_dir.mkdir(parents=True, exist_ok=True)

    print(f"Syncing MCP schemas to {mcp_dir}...")
    tools = await mcp.list_tools()
    active_names = set()

    for t in tools:
        schema = {
            "name": t.name,
            "description": t.description,
            "parameters": t.inputSchema
        }
        output_file = mcp_dir / f"{t.name}.json"
        output_file.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        active_names.add(f"{t.name}.json")
        print(f"  Saved {t.name}.json")

    # Clean up stale schemas
    for f in mcp_dir.glob("*.json"):
        if f.name not in active_names:
            print(f"  Removing stale schema {f.name}")
            f.unlink()

    print("MCP schema sync complete!")

if __name__ == "__main__":
    asyncio.run(main())
