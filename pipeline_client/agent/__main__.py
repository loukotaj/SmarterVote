"""CLI entry point for running the agent as a Cloud Run Job.

Usage:
    python -m pipeline_client.agent <race_id> [--cheap-mode]

Used by the Cloud Run Job (infra/run-job.tf) to process a single race.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
root = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=root / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("pipeline")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run the research agent for a race")
    parser.add_argument("race_id", help="Race slug, e.g. mo-senate-2024")
    parser.add_argument("--cheap-mode", action="store_true", default=True)
    parser.add_argument("--no-cheap-mode", dest="cheap_mode", action="store_false")
    args = parser.parse_args()

    from pipeline_client.agent.agent import run_agent

    def on_log(level: str, message: str) -> None:
        logger.log(getattr(logging, level.upper(), logging.INFO), message)

    logger.info(f"Starting agent for {args.race_id}")
    result = await run_agent(
        args.race_id,
        on_log=on_log,
        cheap_mode=args.cheap_mode,
    )

    # Write result to published dir
    published_dir = root / "data" / "published"
    published_dir.mkdir(parents=True, exist_ok=True)
    out = published_dir / f"{args.race_id}.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    logger.info(f"Published to {out}")


if __name__ == "__main__":
    asyncio.run(main())
