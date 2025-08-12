#!/usr/bin/env python3
"""
Enhanced Pipeline Client startup script with logging configuration.
"""
import logging
import sys
from pathlib import Path

# Add the project root to Python path
root_path = Path(__file__).resolve().parents[1]
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))

# Configure logging before importing other modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

if __name__ == "__main__":
    import uvicorn
    from pipeline_client.backend.main import app
    from pipeline_client.backend.logging_manager import logging_manager

    # Setup the logging manager
    logger = logging_manager.setup_logger("pipeline")
    logger.info("Starting Enhanced Pipeline Client...")

    # Run the application
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info", access_log=True)
