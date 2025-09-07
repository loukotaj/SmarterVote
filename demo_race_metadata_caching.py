#!/usr/bin/env python3
"""
Race Metadata Caching Demo

Demonstrates the caching functionality for race metadata extraction.
"""

import asyncio
import sys
import time
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, "/home/runner/work/SmarterVote/SmarterVote")

from pipeline.app.step01_ingest.MetaDataService.race_metadata_service import RaceMetadataService


async def demo_caching():
    """Demonstrate race metadata caching functionality."""
    print("🗳️  Race Metadata Caching Demo")
    print("=" * 50)

    # Initialize service with caching enabled
    print("\n1. Initializing RaceMetadataService with caching...")
    service = RaceMetadataService(
        enable_caching=True,
        cache_ttl_hours=6,  # 6-hour TTL for demo
    )
    print("✅ Service initialized with caching enabled")

    # Demo race ID
    race_id = "mo-senate-2024"

    try:
        # Show cache stats before
        print("\n2. Initial cache statistics:")
        stats = await service.get_cache_stats()
        print(f"   Total cached items: {stats.get('total_items', 0)}")
        print(f"   Fresh items: {stats.get('fresh_items', 0)}")
        print(f"   Expired items: {stats.get('expired_items', 0)}")
        print(f"   TTL: {stats.get('ttl_hours', 'unknown')} hours")

        # First extraction (cache miss expected)
        print(f"\n3. First extraction for {race_id} (should be cache miss)...")
        start_time = time.perf_counter()

        try:
            race_json = await service.extract_race_metadata(race_id)
            duration = time.perf_counter() - start_time

            print(f"✅ Extraction completed in {duration:.2f} seconds")
            print(f"   Race: {race_json.id}")
            print(f"   Candidates found: {len(race_json.candidates)}")
            if race_json.race_metadata:
                print(f"   State: {race_json.race_metadata.state}")
                print(f"   Office: {race_json.race_metadata.office_type}")
                print(f"   Confidence: {race_json.race_metadata.confidence.value}")

        except Exception as e:
            print(f"❌ Extraction failed: {e}")
            print("   This is expected in demo environment without proper API keys")

        # Second extraction (cache hit expected)
        print(f"\n4. Second extraction for {race_id} (should be cache hit)...")
        start_time = time.perf_counter()

        try:
            race_json = await service.extract_race_metadata(race_id)
            duration = time.perf_counter() - start_time

            print(f"✅ Extraction completed in {duration:.2f} seconds (faster due to cache)")
            print(f"   Race: {race_json.id}")
            print(f"   Candidates found: {len(race_json.candidates)}")

        except Exception as e:
            print(f"❌ Extraction failed: {e}")

        # Force refresh (bypasses cache)
        print(f"\n5. Force refresh for {race_id} (bypasses cache)...")
        start_time = time.perf_counter()

        try:
            race_json = await service.extract_race_metadata(race_id, force_refresh=True)
            duration = time.perf_counter() - start_time

            print(f"✅ Force refresh completed in {duration:.2f} seconds")
            print("   Cache was bypassed as requested")

        except Exception as e:
            print(f"❌ Force refresh failed: {e}")

        # Show final cache stats
        print("\n6. Final cache statistics:")
        stats = await service.get_cache_stats()
        print(f"   Total cached items: {stats.get('total_items', 0)}")
        print(f"   Fresh items: {stats.get('fresh_items', 0)}")
        print(f"   Expired items: {stats.get('expired_items', 0)}")

        # Demonstrate cache management
        print("\n7. Cache management operations:")

        # Cache invalidation
        print("   Testing cache invalidation...")
        success = await service.invalidate_cache(race_id)
        print(f"   Invalidation result: {'✅ Success' if success else '❌ Failed'}")

        # Cleanup expired entries
        print("   Testing cleanup of expired entries...")
        removed_count = await service.cleanup_expired_cache()
        print(f"   Removed {removed_count} expired entries")

        # Bulk invalidation demo
        print("   Testing bulk invalidation...")
        bulk_results = await service.bulk_invalidate_cache([race_id, "ca-governor-2024", "tx-house-01-2024"])
        success_count = sum(1 for success in bulk_results.values() if success)
        print(f"   Bulk invalidation: {success_count}/{len(bulk_results)} successful")

    except Exception as e:
        print(f"❌ Demo failed: {e}")

    finally:
        print("\n8. Cleaning up...")
        await service.close()
        print("✅ Demo completed")


async def demo_cache_comparison():
    """Compare performance with and without caching."""
    print("\n🚀 Performance Comparison Demo")
    print("=" * 40)

    race_id = "fl-senate-2024"

    # Test without caching
    print("\n1. Testing WITHOUT caching...")
    service_no_cache = RaceMetadataService(enable_caching=False)

    try:
        start_time = time.perf_counter()
        await service_no_cache.extract_race_metadata(race_id)
        no_cache_duration = time.perf_counter() - start_time
        print(f"   No cache duration: {no_cache_duration:.2f} seconds")
    except Exception as e:
        print(f"   No cache test failed: {e}")
        no_cache_duration = 0
    finally:
        await service_no_cache.close()

    # Test with caching (first call - cache miss)
    print("\n2. Testing WITH caching (first call - cache miss)...")
    service_with_cache = RaceMetadataService(enable_caching=True)

    try:
        start_time = time.perf_counter()
        await service_with_cache.extract_race_metadata(race_id)
        cache_miss_duration = time.perf_counter() - start_time
        print(f"   Cache miss duration: {cache_miss_duration:.2f} seconds")

        # Second call - cache hit
        print("\n3. Testing WITH caching (second call - cache hit)...")
        start_time = time.perf_counter()
        await service_with_cache.extract_race_metadata(race_id)
        cache_hit_duration = time.perf_counter() - start_time
        print(f"   Cache hit duration: {cache_hit_duration:.2f} seconds")

        if cache_hit_duration > 0 and cache_miss_duration > 0:
            speedup = cache_miss_duration / cache_hit_duration
            print(f"   Speedup from caching: {speedup:.1f}x faster")

    except Exception as e:
        print(f"   Cache test failed: {e}")
    finally:
        await service_with_cache.close()


if __name__ == "__main__":
    print("Starting Race Metadata Caching Demonstration...")
    print("Note: This demo may show errors for actual API calls in test environment")
    print("The caching logic will still be demonstrated even if extraction fails")

    try:
        # Run main demo
        asyncio.run(demo_caching())

        # Run performance comparison
        asyncio.run(demo_cache_comparison())

    except KeyboardInterrupt:
        print("\n❌ Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")

    print("\n🎉 Demo finished!")
