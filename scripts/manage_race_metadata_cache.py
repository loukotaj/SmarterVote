#!/usr/bin/env python3
"""
Race Metadata Cache Management CLI

Command-line utility for managing the race metadata cache.
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, "/home/runner/work/SmarterVote/SmarterVote")

from pipeline.app.utils.race_metadata_cache import RaceMetadataCache

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def view_cache(cache: RaceMetadataCache, race_id: str = None):
    """View cached race metadata."""
    if race_id:
        print(f"📊 Viewing cache for race: {race_id}")
        
        cached_data = await cache.get_cached_metadata(race_id)
        if cached_data:
            print(f"✅ Found cached data for race '{race_id}':")
            print(f"   Candidates: {len(cached_data.candidates)}")
            print(f"   State: {cached_data.race_metadata.state if cached_data.race_metadata else 'Unknown'}")
            print(f"   Office: {cached_data.race_metadata.office_type if cached_data.race_metadata else 'Unknown'}")
            print(f"   Year: {cached_data.race_metadata.year if cached_data.race_metadata else 'Unknown'}")
            print(f"   Confidence: {cached_data.race_metadata.confidence.value if cached_data.race_metadata else 'Unknown'}")
            print(f"   Updated: {cached_data.updated_utc}")
            
            print("\n🏛️ Candidates:")
            for i, candidate in enumerate(cached_data.candidates, 1):
                incumbent_status = " (Incumbent)" if candidate.incumbent else ""
                print(f"   {i}. {candidate.name} ({candidate.party}){incumbent_status}")
        else:
            print(f"❌ No cached data found for race '{race_id}' (or cache expired)")
    else:
        print("📈 Overall cache statistics:")
        stats = await cache.get_cache_stats()
        
        print(f"   Total Items: {stats.get('total_items', 0)}")
        print(f"   Fresh Items: {stats.get('fresh_items', 0)}")
        print(f"   Expired Items: {stats.get('expired_items', 0)}")
        print(f"   TTL Hours: {stats.get('ttl_hours', 'Unknown')}")
        
        if stats.get('oldest_cache'):
            print(f"   Oldest Cache: {stats['oldest_cache']}")
        if stats.get('newest_cache'):
            print(f"   Newest Cache: {stats['newest_cache']}")
        
        stats_by_year = stats.get("stats_by_year", {})
        if stats_by_year:
            print(f"\n📅 Cache by Year:")
            for year, count in sorted(stats_by_year.items()):
                print(f"   {year}: {count} races")
        
        stats_by_state = stats.get("stats_by_state", {})
        if stats_by_state:
            print(f"\n🗺️  Cache by State:")
            for state, count in sorted(stats_by_state.items()):
                print(f"   {state}: {count} races")


async def clear_cache(cache: RaceMetadataCache, race_id: str = None, confirm: bool = False):
    """Clear cached race metadata."""
    if race_id:
        print(f"🗑️  Clearing cache for race: {race_id}")
    else:
        print("🗑️  Clearing ALL cached race metadata")
    
    if not confirm:
        response = input("Are you sure? This cannot be undone. (y/N): ")
        if response.lower() != "y":
            print("Operation cancelled.")
            return
    
    if race_id:
        success = await cache.invalidate_cache(race_id)
        if success:
            print("✅ Cache cleared successfully")
        else:
            print("❌ Failed to clear cache")
    else:
        # For bulk clear, we need to get all race IDs first
        stats = await cache.get_cache_stats()
        if stats.get('total_items', 0) == 0:
            print("✅ No items to clear")
            return
        
        # This is a simplified bulk clear - in a real implementation, 
        # you might want to query all document IDs and then batch delete
        print("❌ Bulk clear all not implemented. Please specify race IDs individually.")


async def test_connection(cache: RaceMetadataCache):
    """Test cache connection."""
    print("🔗 Testing race metadata cache connection...")
    
    try:
        stats = await cache.get_cache_stats()
        print("✅ Connection successful")
        print(f"   Found {stats.get('total_items', 0)} cached race metadata entries")
        print(f"   TTL set to {stats.get('ttl_hours', 'unknown')} hours")
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")


async def cleanup_expired(cache: RaceMetadataCache):
    """Cleanup expired cache entries."""
    print("🧹 Cleaning up expired cache entries...")
    
    try:
        removed_count = await cache.cleanup_expired_entries()
        if removed_count > 0:
            print(f"✅ Removed {removed_count} expired entries")
        else:
            print("✅ No expired entries found")
            
    except Exception as e:
        print(f"❌ Cleanup failed: {e}")


async def export_cache(cache: RaceMetadataCache, race_id: str, output_file: str):
    """Export cached race metadata to JSON file."""
    print(f"📤 Exporting cache for race '{race_id}' to {output_file}")
    
    cached_data = await cache.get_cached_metadata(race_id)
    
    if not cached_data:
        print(f"❌ No cached data found for race '{race_id}'")
        return
    
    # Prepare export data
    export_data = {
        "export_timestamp": datetime.utcnow().isoformat(),
        "race_id": race_id,
        "race_data": cached_data.model_dump(mode="json", by_alias=True, exclude_none=True),
    }
    
    # Write to file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, default=str)
    
    print(f"✅ Exported race metadata to {output_file}")


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Race Metadata Cache Management Utility")
    parser.add_argument("--project-id", help="Google Cloud Project ID")
    parser.add_argument("--collection", default="race_metadata_cache", help="Firestore collection name")
    parser.add_argument("--ttl-hours", type=int, default=12, help="Default TTL in hours")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # View command
    view_parser = subparsers.add_parser("view", help="View cached race metadata")
    view_parser.add_argument("--race-id", help="Specific race ID to view")
    
    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear cached race metadata")
    clear_parser.add_argument("--race-id", help="Specific race ID to clear")
    clear_parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")
    
    # Test command
    subparsers.add_parser("test", help="Test cache connection")
    
    # Cleanup command
    subparsers.add_parser("cleanup", help="Remove expired cache entries")
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export cached race metadata to JSON")
    export_parser.add_argument("race_id", help="Race ID to export")
    export_parser.add_argument("output_file", help="Output JSON file path")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize cache
    cache = RaceMetadataCache(
        project_id=args.project_id,
        collection_name=args.collection,
        default_ttl_hours=args.ttl_hours
    )
    
    try:
        if args.command == "view":
            await view_cache(cache, args.race_id)
        elif args.command == "clear":
            await clear_cache(cache, args.race_id, args.confirm)
        elif args.command == "test":
            await test_connection(cache)
        elif args.command == "cleanup":
            await cleanup_expired(cache)
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