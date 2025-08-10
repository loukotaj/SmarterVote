#!/usr/bin/env python3
"""
Install shared schema package in development mode.
Run this before developing on pipeline or services.
"""

import subprocess
import sys
from pathlib import Path


def main():
    project_root = Path(__file__).parent.parent
    shared_path = project_root / "shared"

    if not shared_path.exists():
        print("❌ Shared schema package not found")
        return 1

    print("📦 Installing shared schema package in development mode...")
    result = subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(shared_path)])

    if result.returncode == 0:
        print("✅ Shared schema package installed successfully")
        print("You can now import from 'shared' in your code")
    else:
        print("❌ Failed to install shared schema package")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
