#!/usr/bin/env python3
"""
Setup script for SmarterVote development environment.
Installs pre-commit hooks and ensures proper development setup.
"""

import subprocess
import sys
from pathlib import Path


def run_command(command: str, description: str) -> bool:
    """Run a command and return success status."""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(command.split(), check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        print(f"   Command: {command}")
        print(f"   Error: {e.stderr}")
        return False


def main():
    """Main setup function."""
    print("🚀 Setting up SmarterVote development environment...")

    # Check if we're in the right directory
    if not Path(".pre-commit-config.yaml").exists():
        print("❌ Error: .pre-commit-config.yaml not found. Are you in the project root?")
        sys.exit(1)

    # Install pre-commit if not already installed
    success = True

    # Install pre-commit hooks
    success &= run_command("pre-commit install", "Installing pre-commit hooks")

    # Install commit-msg hook for conventional commits (optional)
    success &= run_command("pre-commit install --hook-type commit-msg", "Installing commit-msg hook")

    # Run pre-commit on all files to ensure everything is properly formatted
    print("🔧 Running pre-commit on all files (this may take a moment)...")
    try:
        subprocess.run(["pre-commit", "run", "--all-files"], check=True)
        print("✅ All files are properly formatted")
    except subprocess.CalledProcessError:
        print("⚠️  Some files needed formatting. Please review and commit the changes.")
        success = False

    if success:
        print("\n🎉 Development environment setup complete!")
        print("📝 Pre-commit hooks will now run automatically before each commit.")
        print("💡 To manually run all hooks: pre-commit run --all-files")
    else:
        print("\n⚠️  Setup completed with some issues. Please review the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
