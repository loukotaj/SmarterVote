"""Integration test for RaceMetadataService caching functionality."""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from pipeline.app.step01_ingest.MetaDataService.race_metadata_service import RaceMetadataService


class TestRaceMetadataServiceCaching:
    """Test caching integration in RaceMetadataService."""

    @pytest.mark.asyncio
    async def test_service_initialization_with_caching(self):
        """Test that service initializes properly with caching enabled."""
        with patch("pipeline.app.step01_ingest.MetaDataService.race_metadata_service.RaceMetadataCache") as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache_class.return_value = mock_cache

            service = RaceMetadataService(
                enable_caching=True,
                cache_ttl_hours=6,
                cache_project_id="test-project"
            )

            assert service.enable_caching is True
            assert service.cache is not None
            mock_cache_class.assert_called_once_with(
                project_id="test-project",
                collection_name="race_metadata_cache",
                default_ttl_hours=6,
            )

    @pytest.mark.asyncio
    async def test_service_initialization_without_caching(self):
        """Test that service initializes properly with caching disabled."""
        service = RaceMetadataService(enable_caching=False)

        assert service.enable_caching is False
        assert service.cache is None

    @pytest.mark.asyncio
    async def test_cache_management_methods(self):
        """Test cache management utility methods."""
        with patch("pipeline.app.step01_ingest.MetaDataService.race_metadata_service.RaceMetadataCache") as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache_class.return_value = mock_cache
            
            # Setup mock return values
            mock_cache.invalidate_cache.return_value = True
            mock_cache.bulk_invalidate_cache.return_value = {"race1": True, "race2": True}
            mock_cache.get_cache_stats.return_value = {"total_items": 5}
            mock_cache.cleanup_expired_entries.return_value = 2

            service = RaceMetadataService(enable_caching=True)

            # Test invalidate_cache
            result = await service.invalidate_cache("test-race")
            assert result is True
            mock_cache.invalidate_cache.assert_called_once_with("test-race")

            # Test bulk_invalidate_cache
            result = await service.bulk_invalidate_cache(["race1", "race2"])
            assert result == {"race1": True, "race2": True}
            mock_cache.bulk_invalidate_cache.assert_called_once_with(["race1", "race2"])

            # Test get_cache_stats
            result = await service.get_cache_stats()
            assert result["total_items"] == 5
            assert result["caching_enabled"] is True
            mock_cache.get_cache_stats.assert_called_once()

            # Test cleanup_expired_cache
            result = await service.cleanup_expired_cache()
            assert result == 2
            mock_cache.cleanup_expired_entries.assert_called_once()

            # Test close
            await service.close()
            mock_cache.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_management_methods_disabled(self):
        """Test cache management methods when caching is disabled."""
        service = RaceMetadataService(enable_caching=False)

        # All cache management methods should work gracefully when caching is disabled
        result = await service.invalidate_cache("test-race")
        assert result is True

        result = await service.bulk_invalidate_cache(["race1", "race2"])
        assert result == {"race1": True, "race2": True}

        result = await service.get_cache_stats()
        assert result == {"caching_enabled": False}

        result = await service.cleanup_expired_cache()
        assert result == 0

        # Close should not error
        await service.close()

    @pytest.mark.asyncio
    async def test_extract_race_metadata_force_refresh(self):
        """Test that force_refresh bypasses cache."""
        with patch("pipeline.app.step01_ingest.MetaDataService.race_metadata_service.RaceMetadataCache") as mock_cache_class:
            mock_cache = AsyncMock()
            mock_cache_class.return_value = mock_cache
            
            service = RaceMetadataService(enable_caching=True)

            # Mock the internal methods to avoid actual external calls
            with patch.object(service, '_parse_race_id', return_value=("CA", "senate", 2024, None, None)), \
                 patch.object(service, '_seed_urls', return_value=[]), \
                 patch.object(service, '_fetch_and_extract_docs', return_value=[]), \
                 patch.object(service, '_llm_candidates', return_value=([], None, [])), \
                 patch.object(service, '_empty_meta') as mock_empty_meta:
                
                mock_empty_meta.return_value = AsyncMock()

                # Call with force_refresh=True
                try:
                    await service.extract_race_metadata("ca-senate-2024", force_refresh=True)
                except Exception:
                    # Expected to fail due to mocking, but cache should not be checked
                    pass

                # Cache get should not be called when force_refresh=True
                mock_cache.get_cached_metadata.assert_not_called()


if __name__ == "__main__":
    # Run basic async test
    async def basic_test():
        print("Testing RaceMetadataService caching integration...")
        
        # Test service initialization
        service = RaceMetadataService(enable_caching=True, cache_ttl_hours=6)
        print(f"Caching enabled: {service.enable_caching}")
        print(f"Cache object created: {service.cache is not None}")
        
        # Test disabled caching
        service_no_cache = RaceMetadataService(enable_caching=False)
        print(f"Caching disabled: {not service_no_cache.enable_caching}")
        print(f"No cache object: {service_no_cache.cache is None}")
        
        print("Basic integration test passed!")

    asyncio.run(basic_test())