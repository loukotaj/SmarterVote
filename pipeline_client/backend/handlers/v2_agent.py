"""Pipeline V2 handler: single-step agent-based candidate research.

Wraps the v2 agent as a pipeline step handler so it integrates with
the existing pipeline_client execution engine, storage, and logging.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class V2AgentHandler:
    """Handler that runs the v2 research agent and publishes RaceJSON."""

    def __init__(self, storage_backend=None):
        self.storage_backend = storage_backend

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        """Run the v2 agent for a race_id and publish the result.

        Payload expected:
            - race_id: str (e.g. "mo-senate-2024")

        Options:
            - cheap_mode: bool (default True, uses gpt-4o-mini)

        Returns:
            dict with race_id, race_json, published_path, duration_ms, search_count
        """
        from pipeline_v2.agent import run_agent

        logger = logging.getLogger("pipeline")
        race_id = payload.get("race_id")
        if not race_id:
            raise ValueError("V2AgentHandler: Missing 'race_id' in payload")

        cheap_mode = options.get("cheap_mode", True)
        t0 = time.perf_counter()

        logger.info(f"V2 Agent: researching race {race_id} (cheap_mode={cheap_mode})")

        # Collect logs from the agent
        agent_logs: list[Dict[str, Any]] = []

        def on_log(level: str, message: str) -> None:
            agent_logs.append(
                {
                    "level": level,
                    "message": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        # Run the agent
        race_json = await run_agent(
            race_id,
            on_log=on_log,
            cheap_mode=cheap_mode,
        )

        # Publish to local filesystem
        published_path = await self._publish(race_id, race_json)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(f"V2 Agent: published {race_id} to {published_path} in {duration_ms}ms")

        return {
            "race_id": race_id,
            "race_json": race_json,
            "published_path": str(published_path),
            "duration_ms": duration_ms,
            "agent_logs": agent_logs,
            "status": "published",
        }

    async def _publish(self, race_id: str, race_json: Dict[str, Any]) -> Path:
        """Write RaceJSON to the published data directory."""
        published_dir = Path(__file__).resolve().parents[2] / "data" / "published"
        published_dir.mkdir(parents=True, exist_ok=True)

        output_path = published_dir / f"{race_id}.json"

        # Backup existing file if present
        if output_path.exists():
            backup_path = output_path.with_suffix(
                f".json.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            output_path.rename(backup_path)

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(race_json, f, indent=2, default=str)

        return output_path
