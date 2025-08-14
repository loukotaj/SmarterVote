#!/usr/bin/env python3
"""
Firestore Cache Management Utility

This script provides command-line utilities for managing the Firestore cache.
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime

from firestore_cache import FirestoreCache

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def view_cache(cache: FirestoreCache, race_id: str = None):
    """View cached content."""
    print(f"📊 Viewing cache content for race: {race_id or 'ALL'}")

    if race_id:
        cached_content = await cache.get_cached_content(race_id)
        print(f"\nFound {len(cached_content)} cached items for race '{race_id}':")

        for i, item in enumerate(cached_content, 1):
            print(f"\n{i}. Source: {item.get('source_url', 'Unknown')}")
            print(f"   Text Length: {len(item.get('text', ''))} characters")
            print(f"   Word Count: {item.get('word_count', 'Unknown')}")
            print(f"   Language: {item.get('language', 'Unknown')}")
            print(f"   Cached At: {item.get('cached_at', 'Unknown')}")
            print(f"   Checksum: {item.get('content_checksum', 'Unknown')[:16]}...")

            # Show first 100 chars of text
            text = item.get("text", "")
            preview = text[:100] + "..." if len(text) > 100 else text
            print(f"   Preview: {preview}")

    else:
        stats = await cache.get_cache_stats()
        print(f"\n📈 Overall Cache Statistics:")
        print(f"   Total Items: {stats.get('total_items', 0)}")
        print(f"   Total Text Characters: {stats.get('total_text_chars', 0):,}")
        print(f"   Average Text Length: {stats.get('avg_text_length', 0):.1f}")

        race_breakdown = stats.get("race_breakdown", {})
        if race_breakdown:
            print(f"\n🏁 Race Breakdown:")
            for race, count in sorted(race_breakdown.items()):
                print(f"   {race}: {count} items")


async def clear_cache(cache: FirestoreCache, race_id: str = None, confirm: bool = False):
    """Clear cached content."""
    if race_id:
        print(f"🗑️  Clearing cache for race: {race_id}")
    else:
        print("🗑️  Clearing ALL cached content")

    if not confirm:
        response = input("Are you sure? This cannot be undone. (y/N): ")
        if response.lower() != "y":
            print("Operation cancelled.")
            return

    success = await cache.clear_cache(race_id)
    if success:
        print("✅ Cache cleared successfully")
    else:
        print("❌ Failed to clear cache")


async def test_connection(cache: FirestoreCache):
    """Test Firestore connection."""
    print("🔗 Testing Firestore connection...")

    try:
        # Try to get stats (minimal operation)
        stats = await cache.get_cache_stats()
        print("✅ Connection successful")
        print(f"   Found {stats.get('total_items', 0)} total cached items")

        # Test write operation (create a small test document)
        test_race_id = f"connection-test-{int(datetime.utcnow().timestamp())}"
        from ..schema import ExtractedContent, Source, SourceType

        test_source = Source(
            url="https://test.connection.com",
            source_type=SourceType.WEBSITE,
            title="Connection Test",
            description="Test connection to Firestore",
        )

        test_content = ExtractedContent(
            source=test_source,
            text="This is a connection test.",
            metadata={
                "content_checksum": f"test{int(datetime.utcnow().timestamp())}",
                "test": True,
            },
            extraction_timestamp=datetime.utcnow(),
            word_count=5,
            language="en",
        )

        write_success = await cache.cache_content(test_race_id, [test_content])
        if write_success:
            print("✅ Write test successful")

            # Clean up test data
            await cache.clear_cache(test_race_id)
            print("✅ Cleanup successful")
        else:
            print("❌ Write test failed")

    except Exception as e:
        print(f"❌ Connection failed: {e}")


async def export_cache(cache: FirestoreCache, race_id: str, output_file: str):
    """Export cached content to JSON file."""
    print(f"📤 Exporting cache for race '{race_id}' to {output_file}")

    cached_content = await cache.get_cached_content(race_id)

    if not cached_content:
        print(f"No cached content found for race '{race_id}'")
        return

    # Prepare export data
    export_data = {
        "export_timestamp": datetime.utcnow().isoformat(),
        "race_id": race_id,
        "total_items": len(cached_content),
        "items": cached_content,
    }

    # Write to file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, default=str)

    print(f"✅ Exported {len(cached_content)} items to {output_file}")


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Firestore Cache Management Utility")
    parser.add_argument("--project-id", help="Google Cloud Project ID")
    parser.add_argument("--collection", default="extracted_content_cache", help="Firestore collection name")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # View command
    view_parser = subparsers.add_parser("view", help="View cached content")
    view_parser.add_argument("--race-id", help="Specific race ID to view")

    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear cached content")
    clear_parser.add_argument("--race-id", help="Specific race ID to clear")
    clear_parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")

    # Test command
    subparsers.add_parser("test", help="Test Firestore connection")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export cached content to JSON")
    export_parser.add_argument("race_id", help="Race ID to export")
    export_parser.add_argument("output_file", help="Output JSON file path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Initialize cache
    cache = FirestoreCache(project_id=args.project_id, collection_name=args.collection)

    try:
        if args.command == "view":
            await view_cache(cache, args.race_id)
        elif args.command == "clear":
            await clear_cache(cache, args.race_id, args.confirm)
        elif args.command == "test":
            await test_connection(cache)
        elif args.command == "export":
            await export_cache(cache, args.race_id, args.output_file)
        else:
            print(f"Unknown command: {args.command}")
            parser.print_help()

    except Exception as e:
        logger.error(f"Command failed: {e}")
        print(f"❌ Error: {e}")

    finally:
        await cache.close()


if __name__ == "__main__":
    asyncio.run(main())
